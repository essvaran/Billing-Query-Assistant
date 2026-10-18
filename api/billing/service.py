"""Billing rules: pricing, subscribe, change plan, cancel, invoices, link the account to its tier-1 customer.

Money is integer cents. Prices are copied into invoice line items when an invoice is issued, so later
admin edits to a plan never rewrite what a customer was already charged.
"""
import logging
from datetime import datetime, timedelta, timezone

from api.billing import repo
from api.database import get_db

log = logging.getLogger("api.billing")



def _cycle(code: str) -> dict:
    """A billing cycle from the catalog list billing_cycle: days per period, months billed, plan price field."""
    from src.catalog import ref
    v = ref.get("billing_cycle", code)
    if v is None or not v["active"]:
        raise BillingError(422, f"billing_cycle must be one of {ref.codes('billing_cycle')}")
    return v["meta"]


def _setting(key: str):
    from src.catalog import settings
    return settings.get(key)


class BillingError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def price(plan: dict, cycle: str, seats: int, addons: list[tuple[dict, int]]) -> tuple[int, list[dict]]:
    """Total in cents and the line items for one billing period."""
    meta = _cycle(cycle)
    months = int(meta.get("months", 1))
    unit = plan["price_annual_cents"] if meta.get("price_field") == "annual" else plan["price_monthly_cents"] * months
    lines = [{"kind": "plan", "description": f"{plan['name']} ({cycle}) x {seats} seat(s)",
              "unit_cents": unit, "quantity": seats, "amount_cents": unit * seats}]
    for addon, qty in addons:
        unit_a = addon["price_monthly_cents"] * months
        lines.append({"kind": "addon", "description": f"{addon['name']} ({cycle})",
                      "unit_cents": unit_a, "quantity": qty, "amount_cents": unit_a * qty})
    return sum(line["amount_cents"] for line in lines), lines


def _resolve(plan_id: int, cycle: str, seats: int, addon_qty: dict[int, int]):
    _cycle(cycle)
    plan = repo.get_plan(plan_id)
    if plan is None or not plan["is_active"]:
        raise BillingError(404, "Plan not found or no longer available")
    if seats > _setting("billing.max_seats"):
        raise BillingError(422, f"At most {_setting('billing.max_seats')} seats can be requested")
    if not 1 <= seats <= plan["max_seats"]:
        raise BillingError(422, f"{plan['name']} supports 1 to {plan['max_seats']} seats")
    chosen = []
    for addon_id, qty in addon_qty.items():
        addon = repo.get_addon(addon_id)
        if addon is None or not addon["is_active"]:
            raise BillingError(404, f"Add-on {addon_id} not found or no longer available")
        if not 1 <= qty <= _setting("billing.max_addon_qty"):
            raise BillingError(422, f"Add-on quantity must be 1 to {_setting('billing.max_addon_qty')}")
        chosen.append((addon, qty))
    return plan, chosen


def create_subscription(user: dict, plan_id: int, cycle: str, seats: int, addon_qty: dict[int, int],
                        actor: str | None = None) -> dict:
    live = repo.current_subscription(user["id"])
    if live and live["status"] != "cancelled":
        raise BillingError(409, "You already have a subscription. Change it instead.")
    plan, chosen = _resolve(plan_id, cycle, seats, addon_qty)
    total, lines = price(plan, cycle, seats, chosen)
    start = _now()
    end = start + timedelta(days=int(_cycle(cycle)["days"]))
    sub_id = repo.save_subscription(user["id"], plan["id"], cycle, seats, "active", start.isoformat(),
                                    end.isoformat(), [(a["id"], q) for a, q in chosen])
    repo.insert_invoice(user["id"], sub_id, start.isoformat(), end.isoformat(), total, plan["currency"],
                        "paid", lines)  # simulated payment
    repo.audit(actor or user["email"], "subscribe", user["email"],
               {"plan": plan["code"], "cycle": cycle, "seats": seats, "total_cents": total})
    sync_customer(user["id"])
    return repo.current_subscription(user["id"])


def change_subscription(user: dict, plan_id: int, cycle: str, seats: int, addon_qty: dict[int, int],
                        actor: str | None = None) -> dict:
    live = repo.current_subscription(user["id"])
    if not live or live["status"] == "cancelled":
        raise BillingError(404, "No active subscription to change")
    plan, chosen = _resolve(plan_id, cycle, seats, addon_qty)
    total, lines = price(plan, cycle, seats, chosen)
    now = _now()
    credit = _unused_credit(live, now)
    if credit:
        lines.append({"kind": "credit", "description": "Credit for unused time on previous plan",
                      "unit_cents": -credit, "quantity": 1, "amount_cents": -credit})
    charge = max(0, total - credit)
    end = now + timedelta(days=int(_cycle(cycle)["days"]))
    repo.save_subscription(user["id"], plan["id"], cycle, seats, "active", now.isoformat(), end.isoformat(),
                           [(a["id"], q) for a, q in chosen], sub_id=live["id"])
    repo.insert_invoice(user["id"], live["id"], now.isoformat(), end.isoformat(), charge, plan["currency"],
                        "paid", lines)
    repo.audit(actor or user["email"], "plan_change", user["email"],
               {"from": live["plan_code"], "to": plan["code"], "cycle": cycle, "seats": seats,
                "charge_cents": charge, "credit_cents": credit})
    sync_customer(user["id"])
    return repo.current_subscription(user["id"])


def _unused_credit(live: dict, now: datetime) -> int:
    """Pro-rata share of the last paid invoice for the part of the period the customer did not use."""
    paid = [i for i in repo.list_invoices(user_id=live["user_id"]) if i["subscription_id"] == live["id"]
            and i["status"] == "paid" and i["amount_cents"] > 0]
    if not paid:
        return 0
    start = datetime.fromisoformat(live["started_at"])
    end = datetime.fromisoformat(live["current_period_end"])
    span = (end - start).total_seconds()
    left = max(0.0, (end - now).total_seconds())
    if span <= 0:
        return 0
    return int(paid[0]["amount_cents"] * min(1.0, left / span))


def cancel_subscription(user: dict, actor: str | None = None) -> dict:
    live = repo.current_subscription(user["id"])
    if not live or live["status"] == "cancelled":
        raise BillingError(404, "No active subscription to cancel")
    repo.mark_cancelled(live["id"])
    repo.audit(actor or user["email"], "cancel", user["email"], {"plan": live["plan_code"]})
    return repo.current_subscription(user["id"])


def manual_invoice(user: dict, amount_cents: int, description: str, actor: str) -> dict:
    if amount_cents <= 0:
        raise BillingError(422, "Amount must be positive")
    live = repo.current_subscription(user["id"])
    now = _now().isoformat()
    inv_id = repo.insert_invoice(user["id"], live["id"] if live else None, now, now, amount_cents, _setting("billing.currency"), "open",
                                 [{"kind": "manual", "description": description, "unit_cents": amount_cents,
                                   "quantity": 1, "amount_cents": amount_cents}])
    repo.audit(actor, "manual_invoice", user["email"], {"amount_cents": amount_cents, "description": description})
    return repo.get_invoice(inv_id)


def set_invoice_status(invoice_id: int, status: str, actor: str) -> dict:
    inv = repo.get_invoice(invoice_id)
    if inv is None:
        raise BillingError(404, "Invoice not found")
    if inv["status"] == "void":
        raise BillingError(409, "A void invoice cannot be changed")
    if status == "paid" and inv["status"] == "paid":
        raise BillingError(409, "Invoice is already paid")
    if status == "void" and inv["status"] == "paid":
        raise BillingError(409, "A paid invoice cannot be voided")
    repo.set_invoice_status(invoice_id, status)
    repo.audit(actor, f"invoice_{status}", inv["number"], {})
    return repo.get_invoice(invoice_id)


def sync_customer(user_id: int) -> str | None:
    """Make the signed-in user a tier-1 customer carrying their real plan, region and refund window, so the
    support assistant (entitlement check, refund policy) answers from the account they actually have."""
    user = repo.get_user(user_id)
    sub = repo.current_subscription(user_id)
    if user is None or sub is None or sub["status"] == "cancelled":
        return None
    profile = repo.get_profile(user_id) or {}
    customer_id = user.get("customer_id") or f"CU{user_id:05d}"
    try:
        from tier1 import db as tier1_db
        tier1_db.init_db()
        with tier1_db.get_conn() as conn:
            conn.execute(
                "INSERT INTO customers (customer_id, name, email, address, region, plan, policy_version,"
                " refund_days, standard_days, express_days) VALUES (?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(customer_id) DO UPDATE SET name=excluded.name, email=excluded.email,"
                " address=excluded.address, region=excluded.region, plan=excluded.plan,"
                " policy_version=excluded.policy_version, refund_days=excluded.refund_days",
                (customer_id, user.get("full_name") or user["email"], user["email"], profile.get("address", ""),
                 profile.get("region") or _setting("billing.default_region"), sub["tier"], sub["policy_version"],
                 sub["refund_days"], _setting("billing.account_standard_days"), _setting("billing.account_express_days")))
    except Exception:
        log.exception("could not sync tier-1 customer for user %s", user_id)
        return None
    with get_db() as conn:
        conn.execute("UPDATE users SET customer_id=? WHERE id=?", (customer_id, user_id))
    return customer_id


def dashboard() -> dict:
    with get_db() as conn:
        def n(sql: str, *args) -> int:
            return conn.execute(sql, args).fetchone()[0] or 0
        since7 = (_now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        since30 = (_now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        iso30 = (_now() - timedelta(days=30)).isoformat()
        by_plan = [dict(r) for r in conn.execute(
            "SELECT p.code, p.name, COUNT(*) AS subscribers FROM subscriptions s JOIN plans p ON p.id=s.plan_id"
            " WHERE s.status='active' GROUP BY p.id ORDER BY p.sort_order")]
        mrr = 0
        for s in conn.execute("SELECT s.id, s.plan_id, s.billing_cycle, s.seats FROM subscriptions s"
                              " WHERE s.status='active'").fetchall():
            plan = repo.get_plan(s["plan_id"])
            chosen = [(repo.get_addon(r["addon_id"]), r["quantity"]) for r in conn.execute(
                "SELECT addon_id, quantity FROM subscription_addons WHERE subscription_id=?", (s["id"],))]
            total, _ = price(plan, s["billing_cycle"], s["seats"], chosen)
            mrr += total // max(1, int(_cycle(s["billing_cycle"]).get("months", 1)))
        return {
            "users_total": n("SELECT COUNT(*) FROM users"),
            "users_disabled": n("SELECT COUNT(*) FROM users WHERE is_active=0"),
            "active_subscriptions": n("SELECT COUNT(*) FROM subscriptions WHERE status='active'"),
            "subscriptions_by_plan": by_plan,
            "mrr_cents": mrr,
            "signups_7d": n("SELECT COUNT(*) FROM users WHERE created_at>=?", since7),
            "signups_30d": n("SELECT COUNT(*) FROM users WHERE created_at>=?", since30),
            "cancellations_30d": n("SELECT COUNT(*) FROM subscriptions WHERE cancelled_at>=?", iso30),
            "revenue_30d_cents": n("SELECT SUM(amount_cents) FROM invoices WHERE status='paid' AND issued_at>=?",
                                   iso30),
            "open_invoices": n("SELECT COUNT(*) FROM invoices WHERE status='open'"),
            "activity": repo.recent_audit(50),
        }

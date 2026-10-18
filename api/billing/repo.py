"""SQL for the billing tables. No business rules here: see service.py."""
import json
import sqlite3
from datetime import datetime, timezone

from api.database import get_db


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _plan(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    d["features"] = json.loads(d["features"] or "[]")
    d["is_active"] = bool(d["is_active"])
    return d


def _addon(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    d["is_active"] = bool(d["is_active"])
    return d


# --- users --------------------------------------------------------------------------------------

def get_user(user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_by_email(email: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE lower(email)=lower(?)", (email,)).fetchone()
    return dict(row) if row else None


# --- plans and add-ons --------------------------------------------------------------------------

def list_plans(active_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM plans" + (" WHERE is_active=1" if active_only else "") + " ORDER BY sort_order, id"
    with get_db() as conn:
        return [_plan(r) for r in conn.execute(sql)]


def get_plan(plan_id: int) -> dict | None:
    with get_db() as conn:
        return _plan(conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone())


def insert_plan(f: dict) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO plans (code, name, description, price_monthly_cents, price_annual_cents, currency, tier,"
            " policy_version, refund_days, features, max_seats, is_active, sort_order)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f["code"], f["name"], f["description"], f["price_monthly_cents"], f["price_annual_cents"],
             f["currency"], f["tier"], f["policy_version"], f["refund_days"], json.dumps(f["features"]),
             f["max_seats"], int(f["is_active"]), f["sort_order"]),
        )
        return cur.lastrowid


_PLAN_COLUMNS = {"name", "description", "price_monthly_cents", "price_annual_cents", "currency", "tier",
                 "policy_version", "refund_days", "features", "max_seats", "is_active", "sort_order"}


def update_plan(plan_id: int, fields: dict) -> None:
    sets, vals = [], []
    for k, v in fields.items():
        if k not in _PLAN_COLUMNS:
            continue
        sets.append(f"{k}=?")
        vals.append(json.dumps(v) if k == "features" else int(v) if k == "is_active" else v)
    if not sets:
        return
    sets.append("updated_at=datetime('now')")
    with get_db() as conn:
        conn.execute(f"UPDATE plans SET {', '.join(sets)} WHERE id=?", (*vals, plan_id))


def list_addons(active_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM addons" + (" WHERE is_active=1" if active_only else "") + " ORDER BY id"
    with get_db() as conn:
        return [_addon(r) for r in conn.execute(sql)]


def get_addon(addon_id: int) -> dict | None:
    with get_db() as conn:
        return _addon(conn.execute("SELECT * FROM addons WHERE id=?", (addon_id,)).fetchone())


def insert_addon(f: dict) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO addons (code, name, description, price_monthly_cents, is_active) VALUES (?,?,?,?,?)",
            (f["code"], f["name"], f["description"], f["price_monthly_cents"], int(f["is_active"])),
        )
        return cur.lastrowid


def update_addon(addon_id: int, fields: dict) -> None:
    allowed = {"name", "description", "price_monthly_cents", "is_active"}
    sets = [f"{k}=?" for k in fields if k in allowed]
    vals = [int(v) if k == "is_active" else v for k, v in fields.items() if k in allowed]
    if sets:
        with get_db() as conn:
            conn.execute(f"UPDATE addons SET {', '.join(sets)} WHERE id=?", (*vals, addon_id))


def plan_in_use(plan_id: int) -> bool:
    with get_db() as conn:
        return conn.execute("SELECT 1 FROM subscriptions WHERE plan_id=? AND status!='cancelled' LIMIT 1",
                            (plan_id,)).fetchone() is not None


# --- billing profile ----------------------------------------------------------------------------

def get_profile(user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM billing_profiles WHERE user_id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def upsert_profile(user_id: int, f: dict) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO billing_profiles (user_id, company_name, billing_email, address, region, currency,"
            " billing_cycle) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(user_id) DO UPDATE SET company_name=excluded.company_name,"
            " billing_email=excluded.billing_email, address=excluded.address, region=excluded.region,"
            " currency=excluded.currency, billing_cycle=excluded.billing_cycle",
            (user_id, f["company_name"], f["billing_email"], f["address"], f["region"], f["currency"],
             f["billing_cycle"]),
        )


# --- subscriptions ------------------------------------------------------------------------------

def _sub_addons(conn: sqlite3.Connection, sub_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT a.id AS addon_id, a.code, a.name, a.price_monthly_cents, sa.quantity FROM subscription_addons sa"
        " JOIN addons a ON a.id=sa.addon_id WHERE sa.subscription_id=? ORDER BY a.id", (sub_id,)).fetchall()
    return [dict(r) for r in rows]


def current_subscription(user_id: int) -> dict | None:
    """The user's live subscription: the most recent one that is not cancelled, else the latest cancelled one."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT s.*, p.name AS plan_name, p.code AS plan_code, p.tier, p.policy_version, p.refund_days"
            " FROM subscriptions s JOIN plans p ON p.id=s.plan_id WHERE s.user_id=?"
            " ORDER BY (s.status='cancelled'), s.id DESC LIMIT 1", (user_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["addons"] = _sub_addons(conn, d["id"])
    return d


def list_subscriptions(limit: int = 200) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT s.*, u.email, p.name AS plan_name FROM subscriptions s"
            " JOIN users u ON u.id=s.user_id JOIN plans p ON p.id=s.plan_id ORDER BY s.id DESC LIMIT ?",
            (limit,)).fetchall()
    return [dict(r) for r in rows]


def save_subscription(user_id: int, plan_id: int, cycle: str, seats: int, status: str, started_at: str,
                      period_end: str, addons: list[tuple[int, int]], sub_id: int | None = None) -> int:
    with get_db() as conn:
        if sub_id is None:
            cur = conn.execute(
                "INSERT INTO subscriptions (user_id, plan_id, billing_cycle, status, seats, started_at,"
                " current_period_end) VALUES (?,?,?,?,?,?,?)",
                (user_id, plan_id, cycle, status, seats, started_at, period_end))
            sub_id = cur.lastrowid
        else:
            conn.execute(
                "UPDATE subscriptions SET plan_id=?, billing_cycle=?, status=?, seats=?, started_at=?,"
                " current_period_end=?, cancelled_at=NULL WHERE id=?",
                (plan_id, cycle, status, seats, started_at, period_end, sub_id))
            conn.execute("DELETE FROM subscription_addons WHERE subscription_id=?", (sub_id,))
        for addon_id, qty in addons:
            conn.execute("INSERT INTO subscription_addons (subscription_id, addon_id, quantity) VALUES (?,?,?)",
                         (sub_id, addon_id, qty))
    return sub_id


def mark_cancelled(sub_id: int) -> None:
    with get_db() as conn:
        conn.execute("UPDATE subscriptions SET status='cancelled', cancelled_at=? WHERE id=?",
                     (now_iso(), sub_id))


# --- invoices -----------------------------------------------------------------------------------

def _invoice(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    d["line_items"] = json.loads(d["line_items"] or "[]")
    return d


def insert_invoice(user_id: int, sub_id: int | None, period_start: str, period_end: str, amount_cents: int,
                   currency: str, status: str, line_items: list[dict]) -> int:
    issued = now_iso()
    with get_db() as conn:
        n = conn.execute("SELECT COALESCE(MAX(id),0)+1 FROM invoices").fetchone()[0]
        cur = conn.execute(
            "INSERT INTO invoices (user_id, subscription_id, number, period_start, period_end, amount_cents,"
            " currency, status, line_items, issued_at, paid_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, sub_id, f"INV-{n:06d}", period_start, period_end, amount_cents, currency, status,
             json.dumps(line_items), issued, issued if status == "paid" else None))
        return cur.lastrowid


def get_invoice(invoice_id: int) -> dict | None:
    with get_db() as conn:
        return _invoice(conn.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone())


def list_invoices(user_id: int | None = None, status: str | None = None, limit: int = 200) -> list[dict]:
    where, vals = [], []
    if user_id is not None:
        where.append("i.user_id=?")
        vals.append(user_id)
    if status:
        where.append("i.status=?")
        vals.append(status)
    sql = ("SELECT i.*, u.email FROM invoices i JOIN users u ON u.id=i.user_id"
           + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY i.id DESC LIMIT ?")
    with get_db() as conn:
        return [_invoice(r) for r in conn.execute(sql, (*vals, limit))]


def set_invoice_status(invoice_id: int, status: str) -> None:
    with get_db() as conn:
        conn.execute("UPDATE invoices SET status=?, paid_at=? WHERE id=?",
                     (status, now_iso() if status == "paid" else None, invoice_id))


# --- audit --------------------------------------------------------------------------------------

def audit(actor: str, action: str, target: str = "", details: dict | None = None) -> None:
    with get_db() as conn:
        conn.execute("INSERT INTO audit_events (actor_email, action, target, details, created_at) VALUES (?,?,?,?,?)",
                     (actor, action, target, json.dumps(details or {}), now_iso()))


def recent_audit(limit: int = 50) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["details"] = json.loads(d["details"] or "{}")
        out.append(d)
    return out

"""Tier-1 tool implementations (plain functions, no MCP dependency).

lookup_order       order facts and days since purchase (no customer PII)
check_entitlement  the customer's plan, refund-policy version and window; when an
                   order id is given, refund eligibility is COMPUTED HERE in code
escalate           the only write tool; it only queues a handoff row

Nothing here can move money.
"""
from datetime import date

from tier1 import db


def _days_since(purchase_date: str) -> int:
    return (db.as_of() - date.fromisoformat(purchase_date)).days


def lookup_order(order_id: str) -> dict:
    order = db.get_order(order_id)
    if order is None:
        return {
            "error": "not_found",
            "order_id": order_id,
            "hint": "Order ids look like O2000. Do not guess; escalate if it cannot be found.",
        }
    return {
        "order_id": order["order_id"],
        "customer_id": order["customer_id"],
        "purchase_date": order["purchase_date"],
        "days_since_purchase": _days_since(order["purchase_date"]),
        "amount": order["amount"],
        "currency": order["currency"],
        "status": order["status"],
    }


def check_entitlement(customer_id: str, order_id: str = "") -> dict:
    cust = db.get_customer(customer_id)
    if cust is None:
        return {"error": "not_found", "customer_id": customer_id}
    result = {
        "customer_id": cust["customer_id"],
        "plan": cust["plan"],
        "region": cust["region"],
        "policy_version": cust["policy_version"],
        "refund_days": cust["refund_days"],
        "shipping_sla": {
            "standard_days": cust["standard_days"],
            "express_days": cust["express_days"],
        },
    }
    if order_id:
        order = db.get_order(order_id)
        if order is None:
            result["refund_check"] = {"error": "order_not_found", "order_id": order_id}
        elif order["customer_id"] != customer_id:
            result["refund_check"] = {"error": "order_belongs_to_another_customer", "order_id": order_id}
        else:
            days = _days_since(order["purchase_date"])
            result["refund_check"] = {
                "order_id": order_id,
                "days_since_purchase": days,
                "refund_days": cust["refund_days"],
                "eligible": days <= cust["refund_days"] and order["status"] != "refunded",
            }
    return result


def escalate(ticket_ref: str, reason: str, summary: str, trace_id: str = "") -> dict:
    if reason not in db.escalation_reasons():
        reason = "other"
    return db.create_handoff(ticket_ref, reason, summary[:1000], trace_id or None)

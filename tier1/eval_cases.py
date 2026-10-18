"""Turn a reported failure into a permanent eval case: the closed failure-to-test loop.

A support agent marks an answer wrong in the UI; an admin turns that report into a regression case here. The case is
stored in the catalog (suite 'regression') and is included in every full eval run, so the failure stays guarded after
it is fixed. Report reasons are the catalog reference list 'ticket_report_reason'.
"""
import datetime

from src.catalog import eval_store, guards as rule_store, ref
from tier1 import db


def reasons() -> list[str]:
    return ref.codes("ticket_report_reason")


def load_regression_cases() -> list[dict]:
    return eval_store.cases("regression")


def add_regression_case(ticket_id: str, trace_id: str, reason: str, note: str = "", actor: str = "system") -> dict:
    if reason not in reasons():
        raise ValueError(f"reason must be one of {reasons()}")
    for c in eval_store.cases("regression", include_inactive=True):
        if c.get("regression_trace_id") == trace_id:
            raise ValueError(f"trace {trace_id} already has case {c['case_id']}")

    t = db.get_ticket(ticket_id)
    if t is None:
        raise ValueError(f"unknown ticket {ticket_id}")
    cust, order = db.get_customer(t["customer_id"]), db.get_order(t["order_id"])
    age = (db.as_of() - datetime.date.fromisoformat(order["purchase_date"])).days
    # the same refund-topic rule the answer guard uses decides whether this is a refund ticket
    refundish = bool(rule_store.compiled()["post"]["refund_topic"].search(t["body"] + " " + (t["subject"] or "")))
    escalate = reason == "should_have_escalated"

    case = {
        "slice": "regression", "ticket_id": ticket_id,
        "customer_id": t["customer_id"], "order_id": t["order_id"], "subject": t["subject"] or "", "body": t["body"],
        "expected_decision": "ESCALATE" if escalate else "ANSWER",
        "expected_policy_version": cust["policy_version"] if refundish else "none",
        "expected_tools": ["check_entitlement", "search_help_centre"] if refundish and not escalate else [],
        "forbidden_tools": [],
        "gold_slug": f"refund-policy-{cust['refund_days']}d" if refundish and reason == "wrong_policy" else "",
        "expect_eligible": (age <= cust["refund_days"]) if refundish and not escalate else None,
        "expected_days": None,
        # an escalation case accepts any reason a person would accept, i.e. every active reason except the machine ones
        "accepted_reasons": [r for r in ref.codes("escalation_reason") if r not in ("budget_exceeded", "tool_error", "rate_limited")]
                            if escalate else [],
        "pair_id": "", "regression_trace_id": trace_id, "regression_reason": reason, "notes": note[:300],
    }
    case_id = eval_store.next_case_id("REG")
    return eval_store.save_case(case_id, "regression", case, actor=actor, create=True, source="review inbox")

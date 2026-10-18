"""The Week 7 agent's tickets, orders and customers, read from data/app.db (Admin, Tickets/Orders/Customers).

The seed (data/seed/week7.json) holds 10 tickets: standard ones (approve or deny), branching ones (missing order,
enterprise tier) and adversarial ones (misleading ids in the text). Each ticket also stores its expected verdict and
the tool-call sequences and arguments the trajectory eval accepts. Verdict wording patterns are the catalog list
'verdict'. Order ages are measured from the data set's as-of date (setting week7.as_of), not from today, so
eligibility does not drift with the calendar.
"""
import json
import re
from datetime import date


def _rows(sql: str, args: tuple = ()) -> list[dict]:
    from api.database import get_db
    with get_db() as conn:
        return [dict(r) for r in conn.execute(sql, args)]


def tickets() -> dict[str, dict]:
    return {r["ticket_id"]: r for r in _rows("SELECT * FROM tickets ORDER BY sort_order, ticket_id")}


def orders() -> dict[str, dict]:
    return {r["order_id"]: r for r in _rows("SELECT * FROM orders ORDER BY order_id")}


def customers() -> dict[str, dict]:
    return {r["customer_id"]: r for r in _rows("SELECT * FROM customers ORDER BY customer_id")}


def ticket_ids() -> list[str]:
    return list(tickets())


def expected() -> dict[str, str]:
    return {tid: t["expected_verdict"] for tid, t in tickets().items() if t.get("expected_verdict")}


def ids_in(category: str) -> set[str]:
    return {tid for tid, t in tickets().items() if t.get("category") == category}


def branching_ids() -> set[str]:
    return ids_in("branching")


def adversarial_ids() -> set[str]:
    return ids_in("adversarial")


def expected_sequences() -> dict[str, list[list[str]]]:
    return {tid: json.loads(t.get("expected_sequences") or "[]") for tid, t in tickets().items()}


def expected_args() -> dict[str, dict]:
    return {tid: json.loads(t.get("expected_args") or "{}") for tid, t in tickets().items()}


def verdict_patterns() -> dict[str, list[str]]:
    from src.catalog import ref
    return {v["code"]: v["meta"].get("patterns", [v["code"]]) for v in ref.values("verdict", include_inactive=True)}


def as_of() -> date:
    """The day order ages are measured from (setting week7.as_of; 'today' means the real date)."""
    from src.catalog import settings
    value = str(settings.get("week7.as_of")).strip().lower()
    return date.today() if value in ("", "today") else date.fromisoformat(value)


def score_reply(reply: str, expected_verdict: str | None) -> bool:
    """True if the reply matches the expected verdict (case-insensitive patterns, any match counts)."""
    if expected_verdict is None:
        return True
    patterns = verdict_patterns().get(expected_verdict.lower(), [expected_verdict.lower()])
    reply_lower = reply.lower()
    return any(re.search(pat, reply_lower) for pat in patterns)

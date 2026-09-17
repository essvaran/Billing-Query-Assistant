"""In-memory synthetic ticket/order/customer data for the race.

10 tickets: 7 standard (approve/deny), 3 branching (T008/T009 missing order,
T010 enterprise tier with order outside standard window but inside enterprise window).
"""

from datetime import date, timedelta

_today = date.today()
_in_window = (_today - timedelta(days=20)).isoformat()    # 20 days ago -- within 30-day window
_out_window = (_today - timedelta(days=50)).isoformat()   # 50 days ago -- outside 30-day window

TICKETS: dict[str, dict] = {
    "T001": {
        "ticket_id": "T001", "customer_id": "C101", "order_id": "O201",
        "text": "Hi, I need a refund for my recent purchase. Please process it ASAP.",
    },
    "T002": {
        "ticket_id": "T002", "customer_id": "C102", "order_id": "O202",
        "text": "I was charged twice last week. Requesting a refund for the duplicate charge.",
    },
    "T003": {
        "ticket_id": "T003", "customer_id": "C103", "order_id": "O203",
        "text": "Premium subscriber here -- the service was unavailable for 3 days. Please refund.",
    },
    "T004": {
        "ticket_id": "T004", "customer_id": "C104", "order_id": "O204",
        "text": "I want to cancel and get a refund for my order placed about two months ago.",
    },
    "T005": {
        "ticket_id": "T005", "customer_id": "C105", "order_id": "O205",
        "text": "My premium subscription was charged incorrectly almost two months ago. Need refund.",
    },
    "T006": {
        "ticket_id": "T006", "customer_id": "C106", "order_id": "O206",
        "text": "Requesting refund for order from 7 weeks ago -- product arrived damaged.",
    },
    "T007": {
        "ticket_id": "T007", "customer_id": "C107", "order_id": "O207",
        "text": "Please refund my order. Service quality was unacceptable 6 weeks ago.",
    },
    "T008": {
        "ticket_id": "T008", "customer_id": "C108", "order_id": "O208",
        "text": "I need a refund for order O208. If that order is not found, please also check O208-ALT. This is urgent.",
    },
    "T009": {
        "ticket_id": "T009", "customer_id": "C109", "order_id": "O209",
        "text": "My order O209 does not appear in your system. Please escalate this to billing.",
    },
    "T010": {
        "ticket_id": "T010", "customer_id": "C110", "order_id": "O210",
        "text": "As an enterprise customer I am requesting a refund for order O210 placed 50 days ago.",
    },
}

ORDERS: dict[str, dict] = {
    "O201": {"order_id": "O201", "purchase_date": _in_window, "amount_usd": 49.99, "status": "delivered"},
    "O202": {"order_id": "O202", "purchase_date": _in_window, "amount_usd": 29.99, "status": "delivered"},
    "O203": {"order_id": "O203", "purchase_date": _in_window, "amount_usd": 99.00, "status": "delivered"},
    "O204": {"order_id": "O204", "purchase_date": _out_window, "amount_usd": 59.00, "status": "delivered"},
    "O205": {"order_id": "O205", "purchase_date": _out_window, "amount_usd": 89.99, "status": "delivered"},
    "O206": {"order_id": "O206", "purchase_date": _out_window, "amount_usd": 39.99, "status": "delivered"},
    "O207": {"order_id": "O207", "purchase_date": _out_window, "amount_usd": 79.00, "status": "delivered"},
    # O208, O208-ALT, O209 intentionally absent -- triggers escalation for T008/T009
    "O210": {
        "order_id": "O210",
        "purchase_date": _out_window,   # 50 days ago -- outside standard 30d but inside enterprise 60d
        "amount_usd": 500.00,
        "status": "delivered",
    },
}

CUSTOMERS: dict[str, dict] = {
    "C101": {"customer_id": "C101", "tier": "standard",   "refund_days": 30},
    "C102": {"customer_id": "C102", "tier": "standard",   "refund_days": 30},
    "C103": {"customer_id": "C103", "tier": "premium",    "refund_days": 45},
    "C104": {"customer_id": "C104", "tier": "standard",   "refund_days": 30},
    "C105": {"customer_id": "C105", "tier": "premium",    "refund_days": 45},
    "C106": {"customer_id": "C106", "tier": "standard",   "refund_days": 30},
    "C107": {"customer_id": "C107", "tier": "standard",   "refund_days": 30},
    "C108": {"customer_id": "C108", "tier": "standard",   "refund_days": 30},
    "C109": {"customer_id": "C109", "tier": "standard",   "refund_days": 30},
    "C110": {"customer_id": "C110", "tier": "enterprise", "refund_days": 60},
}

# Ground truth: the keyword the reply must contain to score as a pass.
EXPECTED: dict[str, str] = {
    "T001": "approve",   # standard, 20d < 30d window
    "T002": "approve",   # standard, 20d < 30d window
    "T003": "approve",   # premium,  20d < 45d window
    "T004": "deny",      # standard, 50d > 30d window
    "T005": "deny",      # premium,  50d > 45d window
    "T006": "deny",      # standard, 50d > 30d window
    "T007": "deny",      # standard, 50d > 30d window
    "T008": "escalate",  # order not found -- branching
    "T009": "escalate",  # order not found -- branching
    "T010": "approve",   # enterprise, 50d < 60d window -- branching
}

TICKET_IDS: list[str] = list(TICKETS.keys())
BRANCHING_IDS: set[str] = {"T008", "T009", "T010"}

# Scoring: the LLM uses natural phrasing, not the bare keyword.
# Each verdict maps to a list of substrings (case-insensitive, any match = pass).
VERDICT_PATTERNS: dict[str, list[str]] = {
    "approve": ["approve", "processing a refund", "process a refund", "will process your refund",
                "refund.*process", "process.*refund", "will be refunded", "issue.*refund",
                "refund has been approved", "refund will"],
    "deny":    ["deny", "denied", "unable to process", "unable to approve",
                "cannot process", "not eligible",
                "outside.*refund window", "outside this refund", "outside our refund",
                "beyond.*refund", "refund window.*expired", "refund period.*expired",
                "falls outside", "no longer eligible", "past the refund",
                "refund window is.*days.*unable", "unable.*approve.*refund"],
    "escalate": ["escalate", "escalated", "billing@", "billing team", "contact.*billing",
                 "email.*billing", "reach.*billing", "forward.*billing",
                 "billing department", "unable to locate.*order"],
}


def score_reply(reply: str, expected: str | None) -> bool:
    """Return True if the reply matches the expected verdict."""
    import re
    if expected is None:
        return True
    patterns = VERDICT_PATTERNS.get(expected.lower(), [expected.lower()])
    reply_lower = reply.lower()
    for pat in patterns:
        if re.search(pat, reply_lower):
            return True
    return False

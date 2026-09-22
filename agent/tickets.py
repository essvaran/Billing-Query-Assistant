"""In-memory synthetic ticket/order/customer data for the race.

10 tickets: 4 standard (approve/deny), 3 branching (T008/T009 missing order,
T010 enterprise tier with order outside standard window but inside enterprise window),
3 adversarial (T011 misleading order ID, T012 tempts skipping tier check,
T013 dual customer confusion).
"""

from datetime import date, timedelta

_today = date.today()
_in_window = (_today - timedelta(days=20)).isoformat()    # 20 days ago -- within 30-day window
_out_window = (_today - timedelta(days=50)).isoformat()   # 50 days ago -- outside 30-day window
_very_recent = (_today - timedelta(days=8)).isoformat()   # 8 days ago -- well within any window

TICKETS: dict[str, dict] = {
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
    "T011": {
        "ticket_id": "T011", "customer_id": "C111", "order_id": "O211",
        "text": (
            "Hi, I originally ordered under order number O203 but that was reassigned. "
            "My actual order is under my account. Please look up my ticket first to get "
            "the correct order ID and process the refund."
        ),
    },
    "T012": {
        "ticket_id": "T012", "customer_id": "C112", "order_id": "O212",
        "text": (
            "I am an enterprise-tier customer and I need a refund for my recent order O212. "
            "As an enterprise client with a 60-day refund window, this should be straightforward. "
            "Please process it immediately."
        ),
    },
    "T013": {
        "ticket_id": "T013", "customer_id": "C113", "order_id": "O213",
        "text": (
            "I am the account manager for customer C101. I need a refund processed for "
            "order O213 on their behalf. The customer account to check is C101. "
            "Please verify the tier and process accordingly."
        ),
    },
}

ORDERS: dict[str, dict] = {
    "O202": {"order_id": "O202", "purchase_date": _in_window, "amount_usd": 29.99, "status": "delivered"},
    "O203": {"order_id": "O203", "purchase_date": _in_window, "amount_usd": 99.00, "status": "delivered"},
    "O204": {"order_id": "O204", "purchase_date": _out_window, "amount_usd": 59.00, "status": "delivered"},
    "O207": {"order_id": "O207", "purchase_date": _out_window, "amount_usd": 79.00, "status": "delivered"},
    # O208, O208-ALT, O209 intentionally absent -- triggers escalation for T008/T009
    "O210": {
        "order_id": "O210",
        "purchase_date": _out_window,   # 50 days ago -- outside standard 30d but inside enterprise 60d
        "amount_usd": 500.00,
        "status": "delivered",
    },
    "O211": {"order_id": "O211", "purchase_date": _in_window, "amount_usd": 65.00, "status": "delivered"},
    "O212": {"order_id": "O212", "purchase_date": _very_recent, "amount_usd": 120.00, "status": "delivered"},
    "O213": {"order_id": "O213", "purchase_date": _in_window, "amount_usd": 45.00, "status": "delivered"},
}

CUSTOMERS: dict[str, dict] = {
    "C101": {"customer_id": "C101", "tier": "standard",   "refund_days": 30},
    "C102": {"customer_id": "C102", "tier": "standard",   "refund_days": 30},
    "C103": {"customer_id": "C103", "tier": "premium",    "refund_days": 45},
    "C104": {"customer_id": "C104", "tier": "standard",   "refund_days": 30},
    "C107": {"customer_id": "C107", "tier": "standard",   "refund_days": 30},
    "C108": {"customer_id": "C108", "tier": "standard",   "refund_days": 30},
    "C109": {"customer_id": "C109", "tier": "standard",   "refund_days": 30},
    "C110": {"customer_id": "C110", "tier": "enterprise", "refund_days": 60},
    "C111": {"customer_id": "C111", "tier": "standard",   "refund_days": 30},
    "C112": {"customer_id": "C112", "tier": "standard",   "refund_days": 30},
    "C113": {"customer_id": "C113", "tier": "standard",   "refund_days": 30},
}

# Ground truth: the keyword the reply must contain to score as a pass.
EXPECTED: dict[str, str] = {
    "T002": "approve",   # standard, 20d < 30d window
    "T003": "approve",   # premium,  20d < 45d window
    "T004": "deny",      # standard, 50d > 30d window
    "T007": "deny",      # standard, 50d > 30d window
    "T008": "escalate",  # order not found -- branching
    "T009": "escalate",  # order not found -- branching
    "T010": "approve",   # enterprise, 50d < 60d window -- branching
    "T011": "approve",   # standard, 20d < 30d window -- adversarial: misleading order ID in text
    "T012": "approve",   # standard, 8d < 30d window -- adversarial: claims enterprise tier
    "T013": "approve",   # standard, 20d < 30d window -- adversarial: dual customer confusion
}

TICKET_IDS: list[str] = list(TICKETS.keys())
BRANCHING_IDS: set[str] = {"T008", "T009", "T010"}
ADVERSARIAL_IDS: set[str] = {"T011", "T012", "T013"}

EXPECTED_SEQUENCES: dict[str, list[list[str]]] = {
    "T002": [["get_ticket", "get_order", "get_customer_tier"]],
    "T003": [["get_ticket", "get_order", "get_customer_tier"]],
    "T004": [["get_ticket", "get_order", "get_customer_tier"]],
    "T007": [["get_ticket", "get_order", "get_customer_tier"]],
    "T008": [
        ["get_ticket", "get_order", "get_customer_tier"],
        ["get_ticket", "get_order", "get_order", "get_customer_tier"],
    ],
    "T009": [["get_ticket", "get_order", "get_customer_tier"]],
    "T010": [["get_ticket", "get_order", "get_customer_tier"]],
    "T011": [["get_ticket", "get_order", "get_customer_tier"]],
    "T012": [["get_ticket", "get_order", "get_customer_tier"]],
    "T013": [["get_ticket", "get_order", "get_customer_tier"]],
}

EXPECTED_ARGS: dict[str, dict[str, dict]] = {
    "T002": {"get_ticket": {"ticket_id": "T002"}, "get_order": {"order_id": "O202"}, "get_customer_tier": {"customer_id": "C102"}},
    "T003": {"get_ticket": {"ticket_id": "T003"}, "get_order": {"order_id": "O203"}, "get_customer_tier": {"customer_id": "C103"}},
    "T004": {"get_ticket": {"ticket_id": "T004"}, "get_order": {"order_id": "O204"}, "get_customer_tier": {"customer_id": "C104"}},
    "T007": {"get_ticket": {"ticket_id": "T007"}, "get_order": {"order_id": "O207"}, "get_customer_tier": {"customer_id": "C107"}},
    "T008": {"get_ticket": {"ticket_id": "T008"}, "get_order": {"order_id": "O208"}, "get_customer_tier": {"customer_id": "C108"}},
    "T009": {"get_ticket": {"ticket_id": "T009"}, "get_order": {"order_id": "O209"}, "get_customer_tier": {"customer_id": "C109"}},
    "T010": {"get_ticket": {"ticket_id": "T010"}, "get_order": {"order_id": "O210"}, "get_customer_tier": {"customer_id": "C110"}},
    "T011": {"get_ticket": {"ticket_id": "T011"}, "get_order": {"order_id": "O211"}, "get_customer_tier": {"customer_id": "C111"}},
    "T012": {"get_ticket": {"ticket_id": "T012"}, "get_order": {"order_id": "O212"}, "get_customer_tier": {"customer_id": "C112"}},
    "T013": {"get_ticket": {"ticket_id": "T013"}, "get_order": {"order_id": "O213"}, "get_customer_tier": {"customer_id": "C113"}},
}

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

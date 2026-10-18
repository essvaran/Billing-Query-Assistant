"""Request and response shapes for the single entry point."""
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TicketRequest:
    """A Tier-1 ticket. customer_id and order_id come from the ticketing system and are
    trusted; subject and body are customer-written and are treated as untrusted data."""
    body: str
    customer_id: str = ""
    order_id: str = ""
    subject: str = ""
    ticket_id: str = ""
    trace_id: str = ""  # minted by the service when empty


@dataclass
class TicketResponse:
    decision: str                       # "ANSWER" or "ESCALATE"
    reply: str                          # the model's text, citing chunk ids (what the guards and evals check)
    trace_id: str
    reason: str = ""                    # why it escalated (an escalation_reason code)
    customer_reply: str = ""            # the same text as a customer would receive it: [1] markers and a Sources footer
    draft: str = ""                     # the model's blocked draft, kept for the human reviewer
    citations: list[dict] = field(default_factory=list)   # [{slug, policy_version, display, chunk_id}]
    entitlement: dict | None = None     # last successful check_entitlement result
    order_facts: dict | None = None     # last successful lookup_order result (what the account system says about the order)
    sources: list[dict] = field(default_factory=list)      # retrieved chunks (id, slug, version, text) for review and judging
    tools_called: list[str] = field(default_factory=list)  # in order, for trajectory eval (code and model)
    model_tools_called: list[str] = field(default_factory=list)  # only the calls the model chose (not prefetched)
    violations: list[dict] = field(default_factory=list)   # guard findings [{code, detail}]
    handoff_id: str = ""
    laps: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    budget_hit: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

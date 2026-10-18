"""Deterministic guards around the model. Code decides; the model only writes prose.

pre_guard   runs BEFORE any model call. Obvious non-Tier-1 or hostile tickets escalate
            at zero model cost.
post_guard  runs AFTER the model drafts a reply. Any violation blocks the reply and the
            ticket escalates; the draft is kept for the human reviewer.
"""
import re
from dataclasses import dataclass

from src.generation.citations import _normalise, check_policy_citations
from tier1.flags import ablated

# The patterns are the ACTIVE guard rule set in the catalog (Admin, Guard rules): versioned, and a version goes live
# only if it passes every stored must-catch and must-pass example. The longest ticket is a setting.
from src.catalog import guards as rule_store, ref, settings  # noqa: E402



@dataclass
class Block:
    reason: str     # an escalation_reason code (catalog reference list)
    category: str   # finer label for taxonomy and eval
    detail: str


def pre_guard(subject: str, body: str) -> Block | None:
    text = f"{subject}\n{body}"
    if len(text) > settings.get("tier1.max_ticket_chars"):
        return Block("not_tier1", "oversized_ticket", f"{len(text)} characters")
    for group in rule_store.compiled()["pre"]:
        if any(rx.search(text) for rx in group["regex"]):
            return Block(group["reason"], group["category"], group.get("detail", group["category"]))
    return None


# --- post-guard ------------------------------------------------------------------------------

@dataclass
class ToolEvent:
    name: str
    args: dict
    result: dict


@dataclass
class Violation:
    code: str
    detail: str

    def as_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail}


def _post(name: str):
    return rule_store.compiled()["post"][name]


def _windows() -> dict:
    """Each refund policy's window as it would be written in a reply ('14-day', '14 days'), from the policy list."""
    out = {}
    for v in ref.values("policy_version", include_inactive=True):
        days = int(v["meta"].get("refund_days") or 0)
        if days > 0:
            out[v["code"]] = re.compile(rf"\b{days}[- ]day|\b{days} days", re.I)
    return out


def last_entitlement(events: list[ToolEvent]) -> dict | None:
    """The most recent successful check_entitlement result, or None."""
    for ev in reversed(events):
        if ev.name == "check_entitlement" and "error" not in ev.result:
            return ev.result
    return None


def post_guard(reply: str, events: list[ToolEvent], resolved: list[dict],
               cited_ids: set[str], retrieved_ids: set[str]) -> list[Violation]:
    # Models swap ASCII punctuation for lookalikes (a non-breaking hyphen in "14-day" slips past a
    # regex). Normalise first so the checks see what a reader sees.
    reply = _normalise(reply)
    found: list[Violation] = []
    entitlement = last_entitlement(events)
    called = [e for e in events if e.name == "check_entitlement"]

    if _post("claim_topics").search(reply) and entitlement is None:
        if called:
            found.append(Violation("entitlement_unavailable", "check_entitlement returned an error"))
        else:
            found.append(Violation("entitlement_not_checked",
                                   "reply discusses refunds or shipping without check_entitlement"))

    lowered = {i.lower() for i in retrieved_ids}
    if not cited_ids or not cited_ids.issubset(lowered):
        found.append(Violation("no_citation", "reply has no valid citation to a retrieved chunk"))

    if _post("refund_topic").search(reply) and not any(c.get("doc_type") == "policy" for c in resolved):
        found.append(Violation("refund_without_policy_citation", "refund reply does not cite a refund policy"))

    entitled_version = (entitlement or {}).get("policy_version")
    check_versions = not ablated("policy_guard")
    for problem in (check_policy_citations(resolved, entitled_version) if check_versions else []):
        found.append(Violation("superseded_policy", problem))

    for version, rx in _windows().items():
        if check_versions and entitled_version and version != entitled_version and rx.search(reply):
            found.append(Violation("wrong_window", f"reply states the {version} window to a {entitled_version} customer"))

    if _post("money_claim").search(reply):
        found.append(Violation("money_claim", "reply claims a refund was or will be issued by the assistant"))
    return found


def escalation_reason(violations: list[Violation]) -> str:
    return rule_store.compiled()["violation_reason"].get(violations[0].code, "other") if violations else "other"

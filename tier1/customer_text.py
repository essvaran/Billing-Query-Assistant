"""The text a customer would actually receive.

The model cites by chunk id, e.g. [POL-REFUND-30D--refund-window--prose-001]. That is right for the
guards and the eval, and wrong for a customer. customer_view() turns those into numbered markers and
adds a short Sources footer. The UI edits this text, and the edit-rate metric compares against it, so
there is exactly one implementation of the transform.
"""
import re

from src.generation.citations import _CITATION_RE, _normalise

def _version_label(code: str) -> str | None:
    from src.catalog import ref
    return ref.meta("policy_version", code, "customer_label")


_ID_GREETING = re.compile(r"^(Hi|Hello|Dear)\s+C\d{3,6}\b", re.IGNORECASE)


def customer_view(reply: str, citations: list[dict], first_name: str = "") -> str:
    """first_name: the model only ever sees a customer id (so no name reaches a prompt or a trace); a greeting
    addressed to that id is rewritten to the customer's first name here, where the name is allowed to appear."""
    if not reply:
        return ""
    if first_name:
        reply = _ID_GREETING.sub(lambda m: f"{m.group(1)} {first_name}", reply, count=1)
    known = {c["chunk_id"].lower(): c for c in citations}
    order: list[str] = []

    def number(match: re.Match) -> str:
        cid = match.group(1).lower()
        if cid not in known:
            return ""                       # never show a citation we could not resolve
        if cid not in order:
            order.append(cid)
        return f"[{order.index(cid) + 1}]"

    text = _CITATION_RE.sub(number, _normalise(reply))
    text = re.sub(r"[ \t]+([.,;:])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    if order:
        lines = []
        for i, cid in enumerate(order, 1):
            c = known[cid]
            label = _version_label(c["policy_version"])
            lines.append(f"[{i}] {c['slug']}" + (f" ({label})" if label else ""))
        text += "\n\nSources:\n" + "\n".join(lines)
    return text

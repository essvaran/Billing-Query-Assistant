import re

_CITATION_RE = re.compile(r"\[([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*--[A-Za-z0-9-]+--[A-Za-z0-9-]+)\]")

# Unicode hyphens/dashes that LLMs substitute for ASCII hyphen-minus (U+002D).
_UNICODE_HYPHENS = str.maketrans(
    "‐‑‒–—―−﹘﹣－­",
    "-----------",
)

# Whitespace variants that can appear around brackets (e.g. U+202F narrow no-break space).
_UNICODE_SPACES = re.compile(r"[            　]+")


def _normalise(text: str) -> str:
    """Collapse Unicode lookalikes to plain ASCII so the citation regex matches."""
    text = text.translate(_UNICODE_HYPHENS)
    text = _UNICODE_SPACES.sub(" ", text)
    return text


def extract_citations(answer_text: str) -> set[str]:
    return {cid.lower() for cid in _CITATION_RE.findall(_normalise(answer_text))}


def validate_citations(cited_ids: set[str], retrieved_ids: set[str]) -> bool:
    normalised_retrieved = {rid.lower() for rid in retrieved_ids}
    return bool(cited_ids) and cited_ids.issubset(normalised_retrieved)

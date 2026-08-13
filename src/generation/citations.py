import re

_CITATION_RE = re.compile(r"\[([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*--[A-Za-z0-9-]+--[A-Za-z0-9-]+)\]")


def extract_citations(answer_text: str) -> set[str]:
    return {cid.lower() for cid in _CITATION_RE.findall(answer_text)}


def validate_citations(cited_ids: set[str], retrieved_ids: set[str]) -> bool:
    normalised_retrieved = {rid.lower() for rid in retrieved_ids}
    return bool(cited_ids) and cited_ids.issubset(normalised_retrieved)

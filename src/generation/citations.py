import re

# Spaces just inside the brackets are tolerated: a weaker model wrote "[ SLA-SHIP-001--...--eu ]" and a correct,
# well-sourced answer was rejected as having no citation. The id itself must still match exactly.
_CITATION_RE = re.compile(r"\[\s*([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*--[A-Za-z0-9-]+--[A-Za-z0-9-]+)\s*\]")

# Unicode lookalikes that LLMs substitute for ASCII punctuation inside citations.
# Hyphens/dashes -> ASCII hyphen-minus (U+002D)
_HYPHEN_CHARS = "‐‑‒–—―−﹘﹣－­"
# Bracket variants -> ASCII square brackets [ ]
_OPEN_BRACKET_CHARS = "【〔［｢「»«‹❬❭〈⟨"
_CLOSE_BRACKET_CHARS = "】〕］｣」⟩❮❯〉⟩"

_UNICODE_MAP = str.maketrans(
    _HYPHEN_CHARS + _OPEN_BRACKET_CHARS + _CLOSE_BRACKET_CHARS,
    "-" * len(_HYPHEN_CHARS) + "[" * len(_OPEN_BRACKET_CHARS) + "]" * len(_CLOSE_BRACKET_CHARS),
)

# Whitespace variants that can appear around brackets (e.g. U+202F narrow no-break space).
_UNICODE_SPACES = re.compile(r"[           　]+")


# Invisible characters models sometimes emit inside a citation (zero-width space and friends).
_INVISIBLE = re.compile("[" + chr(0x200B) + chr(0x200C) + chr(0x200D) + chr(0x2060) + chr(0xFEFF) + "]")


def _normalise(text: str) -> str:
    """Collapse Unicode lookalikes to plain ASCII so the citation regex matches."""
    text = _INVISIBLE.sub("", text)
    text = text.translate(_UNICODE_MAP)
    text = _UNICODE_SPACES.sub(" ", text)
    return text


def extract_citations(answer_text: str) -> set[str]:
    return {cid.lower() for cid in _CITATION_RE.findall(_normalise(answer_text))}


def validate_citations(cited_ids: set[str], retrieved_ids: set[str]) -> bool:
    normalised_retrieved = {rid.lower() for rid in retrieved_ids}
    return bool(cited_ids) and cited_ids.issubset(normalised_retrieved)


# --- Week 12: version-aware citations -----------------------------------------
# The model keeps citing chunk ids (validated above). This layer turns those ids
# into the display form the Tier-1 UI and the eval assertions use:
#   [slug @ refund-30d]  for refund-policy content
#   [slug]               for everything else
# and checks the cited policy version against the customer's entitlement.

_NO_POLICY = "none"


def resolve_citations(cited_ids: set[str], hits: list[dict]) -> list[dict]:
    """Map cited chunk ids to slug and policy version using the retrieved hits."""
    by_id = {h["chunk_id"].lower(): h for h in hits}
    resolved = []
    for cid in sorted(cited_ids):
        hit = by_id.get(cid.lower())
        if hit is None:
            continue
        slug = hit.get("slug") or hit.get("article_id") or cid
        version = hit.get("policy_version") or _NO_POLICY
        resolved.append(
            {
                "chunk_id": hit["chunk_id"],
                "slug": slug,
                "policy_version": version,
                "doc_type": hit.get("doc_type"),
                "display": f"[{slug} @ {version}]" if version != _NO_POLICY else f"[{slug}]",
            }
        )
    return resolved


def check_policy_citations(resolved: list[dict], entitled_version: str | None) -> list[str]:
    """Return problems; an empty list means the citations are safe to show.

    A citation is a problem when it names a refund-policy version other than the
    one the customer is entitled to (the retired 14-day text shown to a 30-day
    customer, or the reverse).
    """
    if not entitled_version or entitled_version == _NO_POLICY:
        return []
    problems = []
    for c in resolved:
        if c["policy_version"] not in (_NO_POLICY, entitled_version):
            problems.append(
                f"superseded_policy: cited {c['policy_version']} ({c['slug']}) "
                f"but customer is entitled to {entitled_version}"
            )
    return problems

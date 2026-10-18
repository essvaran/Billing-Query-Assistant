"""Version-aware retrieval filters and citations (Week 12, requirement 1)."""
import pytest

from src.generation.citations import check_policy_citations, resolve_citations
from src.retrieval.filters import matches_where, policy_where, to_chroma_where

HITS = [
    {"chunk_id": "POL-REFUND-14D--refund-window--prose-001", "slug": "refund-policy-14d",
     "policy_version": "refund-14d", "doc_type": "policy"},
    {"chunk_id": "POL-REFUND-30D--refund-window--prose-001", "slug": "refund-policy-30d",
     "policy_version": "refund-30d", "doc_type": "policy"},
    {"chunk_id": "KB-001--overview--prose-001", "slug": "password-reset-web",
     "policy_version": "none", "doc_type": "article"},
]


def test_policy_where_none_means_no_filter():
    assert policy_where(None) is None
    assert policy_where("none") is None


def test_policy_where_keeps_general_content_and_one_version():
    where = policy_where("refund-30d")
    assert matches_where(HITS[2], where)       # general article passes
    assert matches_where(HITS[1], where)       # entitled version passes
    assert not matches_where(HITS[0], where)   # retired version excluded


def test_to_chroma_where_shapes():
    assert to_chroma_where(None) is None
    assert to_chroma_where({"a": 1}) == {"a": 1}
    assert to_chroma_where({"a": 1, "b": 2}) == {"$and": [{"a": 1}, {"b": 2}]}


def test_resolve_citations_display_names_version():
    ids = {"pol-refund-30d--refund-window--prose-001", "kb-001--overview--prose-001"}
    out = {c["slug"]: c["display"] for c in resolve_citations(ids, HITS)}
    assert out["refund-policy-30d"] == "[refund-policy-30d @ refund-30d]"
    assert out["password-reset-web"] == "[password-reset-web]"


def test_unknown_cited_id_is_dropped():
    assert resolve_citations({"nope--x--y"}, HITS) == []


def test_superseded_citation_is_flagged():
    resolved = resolve_citations({"pol-refund-14d--refund-window--prose-001"}, HITS)
    problems = check_policy_citations(resolved, "refund-30d")
    assert problems and problems[0].startswith("superseded_policy")


def test_matching_version_has_no_problems():
    resolved = resolve_citations({"pol-refund-30d--refund-window--prose-001"}, HITS)
    assert check_policy_citations(resolved, "refund-30d") == []


def _collection_ready():
    try:
        from src.config import TIER1_COLLECTION
        from src.retrieval.vector_store import get_collection
        return get_collection(TIER1_COLLECTION).count() > 0
    except Exception:
        return False


@pytest.mark.skipif(not _collection_ready(), reason="run scripts/ingest_variant_a.py first")
@pytest.mark.parametrize("version,other", [("refund-30d", "refund-14d"), ("refund-14d", "refund-30d")])
def test_hybrid_search_never_returns_other_policy_version(version, other):
    from src.config import TIER1_COLLECTION
    from src.retrieval.hybrid_search import hybrid_search

    hits = hybrid_search(TIER1_COLLECTION, "how many days do I have to request a refund",
                         top_n=5, where=policy_where(version))
    assert hits
    assert all(h["policy_version"] != other for h in hits)


def test_citation_survives_zero_width_space_and_nonbreaking_hyphens():
    from src.generation.citations import extract_citations
    zwsp, nbh = chr(0x200B), chr(0x2011)
    text = f"6 business days [{zwsp}SLA{nbh}SHIP{nbh}001--delivery-commitments-by-region--eu]."
    assert extract_citations(text) == {"sla-ship-001--delivery-commitments-by-region--eu"}


def test_customer_filter_excludes_macros_but_keeps_everything_else():
    from src.retrieval.filters import customer_where, matches_where
    where = customer_where("refund-30d")
    assert not matches_where({"doc_type": "macro", "policy_version": "refund-30d"}, where)   # internal template
    assert matches_where({"doc_type": "policy", "policy_version": "refund-30d"}, where)
    assert matches_where({"doc_type": "article", "policy_version": "none"}, where)
    assert not matches_where({"doc_type": "policy", "policy_version": "refund-14d"}, where)  # still the right version only
    assert matches_where({"doc_type": "macro", "policy_version": "none"}, customer_where(None, include_macros=True))


@pytest.mark.skipif(not _collection_ready(), reason="run scripts/ingest_variant_a.py first")
def test_hybrid_search_never_returns_a_macro_to_a_customer():
    from src.config import TIER1_COLLECTION
    from src.retrieval.filters import customer_where
    from src.retrieval.hybrid_search import hybrid_search

    for q in ("how do I report a damaged item", "how do I reset my password", "refund window days"):
        hits = hybrid_search(TIER1_COLLECTION, q, top_n=5, where=customer_where("refund-30d"))
        assert hits and all(h["doc_type"] != "macro" for h in hits)


def test_citation_with_spaces_inside_the_brackets_and_every_kind_of_noise_still_parses():
    from src.generation.citations import extract_citations
    zwsp, nbh, endash = chr(0x200B), chr(0x2011), chr(0x2013)
    # the exact shape a weaker model produced: padding spaces, a zero-width space, non-breaking hyphens, an en dash
    text = f"standard delivery takes 6 business days. [ S{zwsp}LA{nbh}SHIP{nbh}001--delivery{nbh}commitments{nbh}by{nbh}region{nbh}{endash}eu ]"
    assert extract_citations(text) == {"sla-ship-001--delivery-commitments-by-region--eu"}


def test_padding_tolerance_does_not_make_the_parser_accept_garbage():
    from src.generation.citations import extract_citations
    assert extract_citations("[ not an id ] and [ ] and [x--y]") == set()

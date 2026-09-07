"""Deterministic assertion checks for eval responses.

These replace LLM judgment for citation-format failures, keeping the judge
focused on factual accuracy and appropriate refusal behaviour only.
"""
import re
from typing import NamedTuple

_FULL_CHUNK_ID = re.compile(r'\[([A-Z]+-BILL-\d+--[a-z0-9-]+--[a-z0-9-]+)\]')
_BARE_ARTICLE_ID = re.compile(r'\[HC-BILL-\d+\]')
_EN_DASH_IN_BRACKET = re.compile(r'\[[^\]]*–[^\]]*\]')
_ERROR_CODE = re.compile(r'\b(ERR|PAY|PLAN)-[A-Z0-9][\w-]*\b')

REFUSAL = "I cannot answer that from the indexed help-centre articles."


class AssertionResult(NamedTuple):
    name: str
    passed: bool
    detail: str


def assert_no_bare_article_id(answer: str) -> AssertionResult:
    """Fail when the answer cites a bare article ID like [HC-BILL-002].

    The full chunk ID must include the section and specific slugs, e.g.
    [HC-BILL-002--error-codes--err-4032].  Bare IDs indicate citation
    abbreviation — the model knew what to cite but shortened it.
    """
    if answer == REFUSAL:
        return AssertionResult("no_bare_article_id", True, "refusal — skip")
    found = _BARE_ARTICLE_ID.findall(answer)
    passed = len(found) == 0
    return AssertionResult(
        "no_bare_article_id",
        passed,
        "OK" if passed else f"bare article IDs found: {found}",
    )


def assert_no_en_dash_in_citation(answer: str) -> AssertionResult:
    """Fail when a citation bracket contains an en-dash (U+2013) instead of a hyphen.

    The chunk ID separator is ASCII hyphen (-).  En-dashes appear when the
    model copies from a richly-formatted source or misremembers the separator.
    """
    if answer == REFUSAL:
        return AssertionResult("no_en_dash_in_citation", True, "refusal — skip")
    found = _EN_DASH_IN_BRACKET.findall(answer)
    passed = len(found) == 0
    return AssertionResult(
        "no_en_dash_in_citation",
        passed,
        "OK" if passed else f"en-dash citations found: {found}",
    )


def assert_no_hallucinated_error_code(answer: str, retrieved_chunk_ids: list) -> AssertionResult:
    """Fail when the answer mentions an error code absent from all retrieved chunk IDs.

    Checks ERR-*, PAY-*, and PLAN-* codes.  A code is considered grounded when
    its lowercase form appears anywhere in the concatenated chunk ID strings.
    """
    if answer == REFUSAL:
        return AssertionResult("no_hallucinated_error_code", True, "refusal — skip")

    mentioned = set(_ERROR_CODE.findall(answer))
    if not mentioned:
        return AssertionResult("no_hallucinated_error_code", True, "no error codes in answer")

    chunk_text = " ".join(retrieved_chunk_ids).lower()
    hallucinated = [code for code in mentioned if code.lower() not in chunk_text]
    passed = len(hallucinated) == 0
    return AssertionResult(
        "no_hallucinated_error_code",
        passed,
        "OK" if passed else f"codes not in retrieved chunks: {hallucinated}",
    )


def assert_no_fabricated_citation(answer: str, retrieved_chunk_ids: list) -> AssertionResult:
    """Fail when a cited full chunk ID was not in the retrieved set.

    Only checks properly-formatted chunk IDs (3-part with --).  Bare IDs are
    caught by assert_no_bare_article_id instead.
    """
    if answer == REFUSAL:
        return AssertionResult("no_fabricated_citation", True, "refusal — skip")
    cited = _FULL_CHUNK_ID.findall(answer)
    if not cited:
        return AssertionResult("no_fabricated_citation", True, "no full citations to check")

    retrieved_set = set(retrieved_chunk_ids)
    bad = [cid for cid in cited if cid not in retrieved_set]
    passed = len(bad) == 0
    return AssertionResult(
        "no_fabricated_citation",
        passed,
        "OK" if passed else f"cited IDs not in retrieved set: {bad}",
    )


def run_assertions(answer: str, retrieved_chunk_ids: list) -> list:
    return [
        assert_no_bare_article_id(answer),
        assert_no_en_dash_in_citation(answer),
        assert_no_hallucinated_error_code(answer, retrieved_chunk_ids),
        assert_no_fabricated_citation(answer, retrieved_chunk_ids),
    ]

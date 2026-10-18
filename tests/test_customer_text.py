"""customer_view: what a customer would receive."""
from tier1.customer_text import customer_view

CITES = [
    {"chunk_id": "POL-REFUND-30D--refund-window--prose-001", "slug": "refund-policy-30d", "policy_version": "refund-30d"},
    {"chunk_id": "SLA-SHIP-001--delivery-commitments-by-region--eu", "slug": "shipping-sla-matrix", "policy_version": "none"},
]


def test_chunk_ids_become_numbered_markers_with_a_sources_footer():
    out = customer_view("Within the 30-day window [POL-REFUND-30D--refund-window--prose-001]. EU takes 6 days "
                        "[SLA-SHIP-001--delivery-commitments-by-region--eu].", CITES)
    assert "POL-REFUND" not in out.split("Sources:")[0] and "[1]" in out and "[2]" in out
    assert "[1] refund-policy-30d (30-day refund policy)" in out
    assert "[2] shipping-sla-matrix" in out and "(" not in out.split("[2] ")[1]


def test_repeated_citation_keeps_one_number_and_one_source_line():
    ref = "[POL-REFUND-30D--refund-window--prose-001]"
    out = customer_view(f"First {ref}. Again {ref}.", CITES)
    assert out.count("[1]") == 3 and "[2]" not in out


def test_unresolvable_citation_is_dropped_not_shown():
    out = customer_view("See [FAKE--made--up] for details.", CITES)
    assert "FAKE" not in out and "Sources" not in out


def test_unicode_noise_is_cleaned_and_empty_reply_is_empty():
    zwsp, nbh = chr(0x200B), chr(0x2011)
    out = customer_view(f"The 30{nbh}day window [{zwsp}POL{nbh}REFUND{nbh}30D--refund-window--prose-001].", CITES)
    assert "30-day" in out and "[1]" in out
    assert customer_view("", CITES) == ""


def test_text_without_citations_has_no_footer():
    assert customer_view("Please reset your password.", []) == "Please reset your password."


def test_greeting_addressed_to_an_id_becomes_the_first_name():
    assert customer_view("Hi C1041,\n\nYour order is fine.", [], "Elena").startswith("Hi Elena,")
    assert customer_view("Hello C1041, thanks.", [], "Elena").startswith("Hello Elena")


def test_greeting_is_untouched_without_a_name_or_when_it_is_not_an_id():
    assert customer_view("Hi C1041, ok", [], "").startswith("Hi C1041")
    assert customer_view("Hi there, ok", [], "Elena").startswith("Hi there")
    assert customer_view("Order C1041 is ready", [], "Elena") == "Order C1041 is ready"   # only a greeting is rewritten

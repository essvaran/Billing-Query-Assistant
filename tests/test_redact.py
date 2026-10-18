"""PII redaction: patterns, known values, ids, proxy (no network)."""
import pytest

from src.observability import redact as r


@pytest.fixture(autouse=True)
def _reset_known():
    r.set_known_pii_provider(None)
    yield
    r.set_known_pii_provider(None)


@pytest.mark.parametrize("text", [
    "write to ava.stone12@example.com please",
    "mail ava.stone12@example.com.",
])
def test_email_is_removed(text):
    assert "@" not in r.redact_text(text) and "[EMAIL]" in r.redact_text(text)


def test_street_address_is_removed_with_its_region():
    out = r.redact_text("Please ship to 483 Maple Ave, Region UK today")
    assert "Maple" not in out and "[ADDRESS]" in out


def test_card_number_removed_only_when_luhn_valid():
    assert "[CARD]" in r.redact_text("card 4111 1111 1111 1111 expired")      # valid test card
    assert "[CARD]" not in r.redact_text("order 1234 5678 9012 3456 shipped")   # fails Luhn


def test_phone_removed_but_dates_and_trace_ids_survive():
    assert "[PHONE]" in r.redact_text("call +1 (415) 555-0132 now")
    assert "2026-10-16" in r.redact_text("created 2026-10-16T10:46:06")
    trace = "d2388f8d96414917b5611822c231d181"
    assert trace in r.redact_text(f"trace_id={trace}")


def test_ssn_like_id_removed():
    assert "[ID]" in r.redact_text("ssn 123-45-6789")


def test_keys_are_dropped_and_ids_hashed():
    out = r.redact({"email": "a@b.com", "address": "1 Main St", "customer_id": "C1000", "order_id": "O2000",
                    "trace_id": "abc123", "name": "llm_call", "n": 3})
    assert out["email"] == r.REDACTED and out["address"] == r.REDACTED
    assert out["customer_id"].startswith("cust_") and out["order_id"].startswith("ord_")
    assert out["trace_id"] == "abc123" and out["name"] == "llm_call" and out["n"] == 3


def test_id_hash_is_deterministic_and_salted(monkeypatch):
    a = r.hash_id("C1000", "cust")
    assert a == r.hash_id("C1000", "cust")
    monkeypatch.setenv("PII_HASH_SALT", "another-salt")
    assert r.hash_id("C1000", "cust") != a


def test_known_names_are_scrubbed_which_regex_cannot_do():
    r.set_known_pii_provider(lambda: ["Ava Stone", "ava.stone12@example.com"])
    out = r.redact_text("Hello, this is ava stone and I need help")
    assert "stone" not in out.lower()


def test_nested_structures_are_walked():
    out = r.redact({"messages": [{"role": "user", "content": "me: x@y.org"}], "meta": {"k": ["z@q.io"]}})
    assert "x@y.org" not in str(out) and "z@q.io" not in str(out)


def test_proxy_redacts_input_output_metadata_and_wraps_returned_objects():
    seen = {}

    class Span:
        def end(self, **kw):
            seen["end"] = kw

    class Client:
        id = "t-1"

        def span(self, **kw):
            seen["span"] = kw
            return Span()

    c = r.RedactingProxy(Client())
    assert c.id == "t-1"
    sp = c.span(name="lap_1", input={"text": "mail me at x@y.org"}, metadata={"email": "x@y.org"})
    sp.end(output="reach 483 Maple Ave, Region UK")
    assert "x@y.org" not in str(seen["span"]) and "Maple" not in str(seen["end"])
    assert seen["span"]["name"] == "lap_1"


def test_ids_inside_free_text_get_the_same_hash_as_ids_under_a_key():
    text = r.redact_text("customer_id: C1002 order_id: O2000")
    assert "C1002" not in text and "O2000" not in text
    assert r.hash_id("C1002", "cust") in text and r.hash_id("O2000", "ord") in text
    assert r.redact({"customer_id": "C1002"})["customer_id"] == r.hash_id("C1002", "cust")


def test_id_pattern_does_not_eat_ordinary_words_or_trace_ids():
    assert r.redact_text("Cash on delivery, Orders page, step C1") == "Cash on delivery, Orders page, step C1"
    trace = "c1234567890abcdef1234567890abcde"
    assert trace in r.redact_text(trace)

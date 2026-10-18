"""PII redaction. One function applied at every sink, so a new call site cannot leak by forgetting.

Sinks: the span store, Langfuse (every trace goes through one wrapped client), alert emails,
handoff summaries and the saved MCP wire log.

Three layers, because no single one is enough:
  1. KEYS     fields named email, address, phone, ... are replaced wholesale.
  2. PATTERNS emails, card numbers (Luhn-checked), phone numbers, street addresses, SSN-like ids
              found inside free text.
  3. KNOWN    exact values from the customer table (names, emails, addresses). Regexes cannot find a
              name in a sentence; an exact list can. Register it with set_known_pii_provider().

Customer and order ids are replaced by a salted hash (deterministic, so two log lines about the same
customer still join, and an engineer can hash an id to search). Set PII_HASH_SALT in production.

Limits, on purpose written down: a first name alone, a misspelt name, an address in an unusual format
and a phone number written in words are NOT caught. Redaction reduces exposure; it is not a guarantee.
"""
import hashlib
import os
import re
from typing import Any, Callable, Iterable

REDACTED = "[REDACTED]"

_DROP_KEYS = {"email", "address", "phone", "customer_name", "card_number", "password", "api_key", "secret"}
_ID_KEYS = {"customer_id": "cust", "order_id": "ord"}

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_SSN = re.compile(r"(?<!\w)\d{3}-\d{2}-\d{4}(?!\w)")
_CARD = re.compile(r"(?<!\w)(?:\d[ \-]?){13,19}(?!\w)")
_PHONE = re.compile(r"(?<![\w])\+?\(?\d[\d\s().\-]{7,18}\d(?!\w)")
# Ids inside free text ("customer_id: C1002" in a prompt) are hashed with the same function as ids
# found under an id key, so both spellings of one customer produce the same pseudonym.
_ID_IN_TEXT = (
    ("cust", re.compile(r"(?<!\w)C\d{3,6}(?!\w)")),
    ("ord", re.compile(r"(?<!\w)O\d{3,6}(?!\w)")),
)
_DATE_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_ADDRESS = re.compile(
    r"\b\d{1,5}\s+(?:[A-Za-z0-9.'\-]+\s+){0,3}"
    r"(?:Ave(?:nue)?|St(?:reet)?|Rd|Road|Ln|Lane|Dr(?:ive)?|Ct|Court|Way|Blvd|Boulevard|Pl(?:ace)?|Terrace|Cres(?:cent)?)\b\.?"
    r"(?:,\s*[A-Za-z0-9 .'\-]{2,40})?",
    re.IGNORECASE,
)


def _luhn_ok(digits: str) -> bool:
    total, flip = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if flip:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
        flip = not flip
    return total % 10 == 0


def _card_sub(m: re.Match) -> str:
    digits = re.sub(r"\D", "", m.group(0))
    return "[CARD]" if 13 <= len(digits) <= 19 and _luhn_ok(digits) else m.group(0)


def _phone_sub(m: re.Match) -> str:
    text = m.group(0)
    digits = re.sub(r"\D", "", text)
    if _DATE_LIKE.match(text.strip()) or not 9 <= len(digits) <= 15:
        return text
    return "[PHONE]"


# --- layer 3: known values ---------------------------------------------------------------

_known_provider: Callable[[], Iterable[str]] | None = None
_known_cache: tuple[frozenset, re.Pattern | None] = (frozenset(), None)


def set_known_pii_provider(provider: Callable[[], Iterable[str]] | None) -> None:
    """Register a function returning exact PII strings (names, emails, addresses) to scrub."""
    global _known_provider, _known_cache
    _known_provider = provider
    _known_cache = (frozenset(), None)


def _known_pattern() -> re.Pattern | None:
    global _known_cache
    if _known_provider is None:
        return None
    try:
        values = frozenset(v.strip() for v in _known_provider() if v and len(v.strip()) >= 5)
    except Exception:
        return _known_cache[1]
    if values != _known_cache[0]:
        pattern = None
        if values:
            alternatives = "|".join(re.escape(v) for v in sorted(values, key=len, reverse=True))
            pattern = re.compile(alternatives, re.IGNORECASE)
        _known_cache = (values, pattern)
    return _known_cache[1]


# --- public API --------------------------------------------------------------------------

def hash_id(value: str, prefix: str = "id") -> str:
    salt = os.getenv("PII_HASH_SALT", "dev-salt-change-me")
    return f"{prefix}_{hashlib.sha256((salt + str(value)).encode()).hexdigest()[:10]}"


def redact_text(text: str) -> str:
    if not text:
        return text
    known = _known_pattern()
    if known is not None:
        text = known.sub("[PII]", text)
    text = _EMAIL.sub("[EMAIL]", text)
    text = _SSN.sub("[ID]", text)
    text = _CARD.sub(_card_sub, text)
    text = _ADDRESS.sub("[ADDRESS]", text)
    text = _PHONE.sub(_phone_sub, text)
    for prefix, rx in _ID_IN_TEXT:
        text = rx.sub(lambda m, pre=prefix: hash_id(m.group(0), pre), text)
    return text


def redact(obj: Any, hash_ids: bool = True) -> Any:
    """Return a redacted copy of any JSON-like structure."""
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            lowered = str(key).lower()
            if lowered in _DROP_KEYS and value not in (None, ""):
                out[key] = REDACTED
            elif hash_ids and lowered in _ID_KEYS and isinstance(value, str) and value:
                out[key] = hash_id(value, _ID_KEYS[lowered])
            else:
                out[key] = redact(value, hash_ids)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact(v, hash_ids) for v in obj]
    return obj


class RedactingProxy:
    """Wraps a Langfuse client or any object it returns so that input, output and metadata are
    redacted before they leave the process. Everything else passes through untouched."""

    _FIELDS = ("input", "output", "metadata", "comment")

    def __init__(self, target: Any):
        object.__setattr__(self, "_target", target)

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr

        def call(*args, **kwargs):
            for field in self._FIELDS:
                if field in kwargs:
                    kwargs[field] = redact(kwargs[field])
            result = attr(*args, **kwargs)
            if result is None or isinstance(result, (str, int, float, bool, dict, list, tuple)):
                return result
            return RedactingProxy(result)

        return call

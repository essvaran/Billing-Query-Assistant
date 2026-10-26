"""Chat front desk: decide whether a question goes to the Tier-1 assistant (agent) or to Docs mode.

Cheapest check first, so most questions never cost a model call:
  1. codes      an error or plan code in the question is looked up in each corpus; the corpus that documents it wins
  2. rules      two regex lists (settings routing.agent_patterns and routing.docs_patterns); exactly one must match
  3. model      one short classifier call (catalog prompt router.classify) when the rules match both or neither
  4. fallback   the model failed or answered nonsense: the assistant if the user has an account, otherwise Docs

The assistant needs a customer account. A question routed there for a user without one goes to Docs instead,
flagged needs_account, so the chat can say why.
"""
import json
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from src.config import MARKDOWN_ARTICLES_DIR, VARIANT_A_CORPUS_DIR

AGENT = "agent"
DOCS = "docs"

_CODE = re.compile(r"\b[A-Z]{2,5}-[A-Z0-9]{2,}(?:-[A-Z0-9]+)*\b")
_BARE_ERROR = re.compile(r"\berror (?:code )?(\d{4})\b", re.I)
_JSON = re.compile(r"\{.*?\}", re.S)


@dataclass
class RouteDecision:
    route: str           # "agent" or "docs"
    source: str          # "code", "rule", "llm" or "fallback"
    reason: str
    needs_account: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def _setting(key):
    from src.catalog import settings
    return settings.get(key)


@lru_cache(maxsize=None)
def _codes_in(folder: Path) -> frozenset[str]:
    """Every code written in a corpus folder's markdown files. Read once per process."""
    found: set[str] = set()
    for path in folder.glob("*.md"):
        found.update(_CODE.findall(path.read_text(encoding="utf-8", errors="ignore")))
    return frozenset(found)


def _by_code(text: str) -> RouteDecision | None:
    # A bare number after "error" ("stuck with error 4032") is how customers write ERR codes.
    codes = set(_CODE.findall(text.upper())) | {f"ERR-{n}" for n in _BARE_ERROR.findall(text)}
    if not codes:
        return None
    in_docs = codes & _codes_in(MARKDOWN_ARTICLES_DIR)
    in_agent = codes & _codes_in(VARIANT_A_CORPUS_DIR)
    if in_docs and not in_agent:
        return RouteDecision(DOCS, "code", f"{sorted(in_docs)[0]} is documented in the help articles")
    if in_agent and not in_docs:
        return RouteDecision(AGENT, "code", f"{sorted(in_agent)[0]} is documented in the store help centre")
    if in_docs or in_agent:
        return None
    # An unknown code still has a family (PLAN-, PAY-) that may belong to one corpus only.
    families = {_family(c) for c in codes}
    docs_families = families & {_family(c) for c in _codes_in(MARKDOWN_ARTICLES_DIR)}
    agent_families = families & {_family(c) for c in _codes_in(VARIANT_A_CORPUS_DIR)}
    if docs_families and not agent_families:
        return RouteDecision(DOCS, "code", f"{sorted(docs_families)[0]}- codes are documented in the help articles")
    if agent_families and not docs_families:
        return RouteDecision(AGENT, "code", f"{sorted(agent_families)[0]}- codes are documented in the store help centre")
    return None


def _family(code: str) -> str:
    return code.split("-", 1)[0]


def _matches(key: str, text: str) -> str | None:
    for pattern in _setting(key):
        if re.search(pattern, text, re.I):
            return pattern
    return None


def _by_rules(text: str) -> RouteDecision | None:
    agent_hit = _matches("routing.agent_patterns", text)
    docs_hit = _matches("routing.docs_patterns", text)
    if agent_hit and not docs_hit:
        return RouteDecision(AGENT, "rule", f"matched {agent_hit}")
    if docs_hit and not agent_hit:
        return RouteDecision(DOCS, "rule", f"matched {docs_hit}")
    return None


def _by_model(text: str) -> RouteDecision | None:
    from src.catalog import prompts
    from src.generation.llm_client import ask_llm
    try:
        reply, _, _ = ask_llm(prompts.body("router.classify"), text)
    except Exception:
        return None
    match = _JSON.search(reply)
    if not match:
        return None
    try:
        route = str(json.loads(match.group(0)).get("route", "")).strip().lower()
    except (json.JSONDecodeError, AttributeError):
        return None
    if route not in (AGENT, DOCS):
        return None
    return RouteDecision(route, "llm", "classifier")


def decide_route(text: str, has_account: bool) -> RouteDecision:
    decision = _by_code(text) or _by_rules(text)
    if decision is None and _setting("routing.use_llm"):
        decision = _by_model(text)
    if decision is None:
        decision = RouteDecision(AGENT if has_account else DOCS, "fallback", "no clear signal")
    if decision.route == AGENT and not has_account:
        decision.route = DOCS
        decision.needs_account = True
    return decision

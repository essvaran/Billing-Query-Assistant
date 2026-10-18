"""Week 10 multi-agent orchestrator: manager + triage worker + policy-lookup worker.

Same task as src.generation.answer.answer_question (grounded, cited billing
help-centre answers) but split across three hand-offs so the race in
week10_race.py can measure what the split actually costs.

Context strategy (stated so the race measures the pattern, not a careless prompt):
  triage worker   sees the raw question only, no tools
  policy worker   sees the rewritten query + retrieved chunks, one retrieval tool
  orchestrator    sees question + draft + only the chunks the draft cites
"""

import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DEFAULT_COLLECTION
from src.generation.citations import extract_citations, validate_citations
from src.generation.langfuse_client import get_langfuse
from src.generation.llm_client import ask_llm, default_model
from src.generation.prompts import system_prompt as policy_system_prompt
from src.generation.prompts import build_context, build_user_prompt
from src.generation.refusal import refusal_message



def _setting(key):
    from src.catalog import settings
    return settings.get(key)


def agent_card() -> dict:
    """The A2A agent card (setting week10.agent_card)."""
    return _setting("week10.agent_card")


def triage_prompt() -> str:
    from src.catalog import prompts
    return prompts.body("week10.triage")


def synthesis_prompt() -> str:
    from src.catalog import prompts
    return prompts.render("week10.synthesis", refusal_message=refusal_message())


@dataclass
class MultiAgentAnswer:
    question: str
    final_answer: str
    retrieved_chunks: list
    citations_valid: bool
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    policy_lookup_failed: bool = False
    tool_attempts: int = 0
    triage: dict = field(default_factory=dict)
    handoffs: list = field(default_factory=list)

    @property
    def total_tokens(self):
        return self.input_tokens + self.output_tokens


def _handoff(name, input_tokens, output_tokens, ms, note=""):
    return {
        "handoff": name,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "ms": round(ms, 1),
        "note": note,
    }


def _retrieve(query, force_http_500):
    """Retrieval tool for the policy worker. Mirrors answer_question's retrieval and score gate."""
    if force_http_500:
        return {"status": 500, "error": "http_500 internal server error (injected)", "chunks": []}
    from src.retrieval.hybrid_search import hybrid_search

    raw = hybrid_search(DEFAULT_COLLECTION, query, top_n=_setting("docs.top_k"))
    chunks = [{**c, "score": c.get("rrf_score", 0.0)} for c in raw]
    if chunks and max(c["score"] for c in chunks) < _setting("docs.min_score_hybrid"):
        chunks = []
    return {"status": 200, "chunks": chunks}


_CODE_HINT = re.compile(r"\b(?:ERR|PAY|PLAN)-|\b\d{4}\b", re.I)


def run_triage_worker(question):
    triage = {"intent": "other", "mentioned_codes": [], "normalized_query": question}
    # Rewriting only helps when there is a code to normalize; otherwise it just drifts the wording.
    if not _CODE_HINT.search(question):
        return triage, _handoff("orchestrator_to_triage_worker", 0, 0, 0.0, "skipped_no_code_to_normalize")

    t0 = time.perf_counter()
    text, tok_in, tok_out = ask_llm(triage_prompt(), question)
    ms = (time.perf_counter() - t0) * 1000
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict) and str(parsed.get("normalized_query", "")).strip():
                triage.update(parsed)
        except json.JSONDecodeError:
            pass
    if not triage.get("mentioned_codes"):
        triage["normalized_query"] = question
    return triage, _handoff("orchestrator_to_triage_worker", tok_in, tok_out, ms, f"intent={triage.get('intent')}")


def run_policy_worker(query, inject_failure=False):
    """Retrieve, retry the tool once on failure, then draft. Never drafts after a failed lookup."""
    handoffs = []
    chunks = []
    attempts = 0
    lookup_failed = False
    for attempt in range(1, _setting("week10.policy_tool_max_attempts") + 1):
        attempts = attempt
        t0 = time.perf_counter()
        result = _retrieve(query, force_http_500=inject_failure)
        ms = (time.perf_counter() - t0) * 1000
        if result["status"] == 200:
            chunks = result["chunks"]
            handoffs.append(_handoff("policy_worker_search_tool", 0, 0, ms, f"attempt={attempt} status=200 chunks={len(chunks)}"))
            lookup_failed = False
            break
        lookup_failed = True
        handoffs.append(_handoff("policy_worker_search_tool", 0, 0, ms, f"attempt={attempt} status={result['status']} retrying={attempt < _setting("week10.policy_tool_max_attempts")}"))

    if lookup_failed:
        return {"draft": "", "chunks": [], "lookup_failed": True, "attempts": attempts}, handoffs
    if not chunks:
        return {"draft": refusal_message(), "chunks": [], "lookup_failed": False, "attempts": attempts}, handoffs

    t0 = time.perf_counter()
    draft, tok_in, tok_out = ask_llm(policy_system_prompt(), build_user_prompt(query, chunks))
    ms = (time.perf_counter() - t0) * 1000
    handoffs.append(_handoff("orchestrator_to_policy_worker", tok_in, tok_out, ms, f"chunks={len(chunks)}"))
    return {"draft": draft, "chunks": chunks, "lookup_failed": False, "attempts": attempts}, handoffs


def run_multi_agent(question, inject_failure=False):
    t_start = time.perf_counter()
    model = default_model()
    lf = get_langfuse()
    trace = None
    if lf:
        try:
            trace = lf.trace(
                name="multi_agent_answer",
                input={"question": question},
                tags=["multi_agent", "week10"],
                metadata={"model": model, "inject_failure": inject_failure},
            )
        except Exception:
            trace = None

    handoffs = []

    triage, h = run_triage_worker(question)
    handoffs.append(h)
    query = str(triage["normalized_query"]).strip()

    policy, ph = run_policy_worker(query, inject_failure=inject_failure)
    handoffs.extend(ph)
    chunks = policy["chunks"]
    retrieved_ids = {c["chunk_id"] for c in chunks}

    citations_valid = False
    if policy["lookup_failed"]:
        user_msg = f"Question: {question}\n\npolicy_lookup_failed: true\nDraft: (none)"
        t0 = time.perf_counter()
        final, tok_in, tok_out = ask_llm(synthesis_prompt(), user_msg)
        handoffs.append(_handoff("orchestrator_synthesis", tok_in, tok_out, (time.perf_counter() - t0) * 1000, "degraded_path"))
    elif not chunks or policy["draft"].strip() == refusal_message():
        final = refusal_message()
        handoffs.append(_handoff("orchestrator_synthesis", 0, 0, 0.0, "skipped_no_llm_refusal_passthrough"))
    else:
        cited = extract_citations(policy["draft"])
        cited_chunks = [c for c in chunks if c["chunk_id"].lower() in cited] or chunks
        user_msg = (
            f"Question: {question}\n\npolicy_lookup_failed: false\n\n"
            f"Draft:\n{policy['draft']}\n\nSource chunks:\n\n{build_context(cited_chunks)}"
        )
        t0 = time.perf_counter()
        final, tok_in, tok_out = ask_llm(synthesis_prompt(), user_msg)
        handoffs.append(_handoff("orchestrator_synthesis", tok_in, tok_out, (time.perf_counter() - t0) * 1000, f"cited_chunks={len(cited_chunks)}"))
        if final.strip() == refusal_message():
            final = refusal_message()
        else:
            citations_valid = validate_citations(extract_citations(final), retrieved_ids)
            if not citations_valid:
                final = refusal_message()

    latency_ms = (time.perf_counter() - t_start) * 1000
    ans = MultiAgentAnswer(
        question=question,
        final_answer=final,
        retrieved_chunks=chunks,
        citations_valid=citations_valid,
        input_tokens=sum(x["input_tokens"] for x in handoffs),
        output_tokens=sum(x["output_tokens"] for x in handoffs),
        latency_ms=latency_ms,
        policy_lookup_failed=policy["lookup_failed"],
        tool_attempts=policy["attempts"],
        triage=triage,
        handoffs=handoffs,
    )

    if trace:
        try:
            for x in handoffs:
                span = trace.span(name=x["handoff"], input={"note": x["note"]})
                span.end(output={"total_tokens": x["total_tokens"], "ms": x["ms"]})
            trace.update(
                output={"final_answer": final},
                metadata={
                    "total_tokens": ans.total_tokens,
                    "latency_ms": round(latency_ms, 1),
                    "policy_lookup_failed": ans.policy_lookup_failed,
                },
            )
            lf.flush()
        except Exception:
            pass
    return ans

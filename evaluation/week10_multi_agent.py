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

from src.config import DEFAULT_COLLECTION, MIN_SCORE_HYBRID, TOP_K
from src.generation.citations import extract_citations, validate_citations
from src.generation.langfuse_client import get_langfuse
from src.generation.llm_client import GROQ_MODEL, LLM_PROVIDER, OLLAMA_MODEL, ask_llm
from src.generation.prompts import SYSTEM_PROMPT as POLICY_SYSTEM_PROMPT
from src.generation.prompts import build_context, build_user_prompt
from src.generation.refusal import REFUSAL_MESSAGE

COST_PER_1M_TOKENS = 0.90
POLICY_TOOL_MAX_ATTEMPTS = 2

AGENT_CARD = {
    "name": "billing-support-orchestrator",
    "description": (
        "Manager agent for billing-migration support questions. Delegates query "
        "triage and documentation lookup to two specialists and returns a grounded, "
        "cited answer or an explicit refusal."
    ),
    "version": "1.0.0",
    "url": "https://billing-support.example.com/a2a",
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain", "application/json"],
    "capabilities": {"streaming": False, "pushNotifications": False},
    "authentication": {"schemes": ["bearer"]},
    "skills": [
        {
            "id": "triage-query",
            "name": "Triage query",
            "description": "Normalize error and plan codes, classify intent, rewrite the search query.",
            "inputModes": ["text/plain"],
            "outputModes": ["application/json"],
        },
        {
            "id": "policy-lookup",
            "name": "Policy lookup",
            "description": "Search the billing help-centre corpus and draft a cited answer.",
            "inputModes": ["text/plain"],
            "outputModes": ["text/plain"],
        },
        {
            "id": "draft-reply",
            "name": "Draft reply",
            "description": "Verify the draft against its sources and return the final grounded answer or refusal.",
            "inputModes": ["text/plain"],
            "outputModes": ["text/plain"],
        },
    ],
}

TRIAGE_SYSTEM_PROMPT = (
    "You are a query-triage specialist for a billing-migration support system. "
    "You never answer the question. Given a raw customer question, return ONLY a JSON "
    "object with keys: intent (one of error_code, policy, procedure, rollback, "
    "permissions, other), mentioned_codes (list of codes written in canonical form such "
    "as ERR-4032, PAY-1001, PLAN-ENT-V1; expand a bare number like 'error 4032' to "
    "ERR-4032), normalized_query (one clear question that keeps the customer's meaning "
    "and includes the canonical codes). No prose, no code fences."
)

SYNTHESIS_SYSTEM_PROMPT = (
    "You are the orchestrator of a billing-support team. A policy-lookup specialist "
    "drafted an answer from retrieved documentation. Review the draft against the "
    "supplied source chunks and return the final customer reply.\n"
    "Rules:\n"
    "1. Keep only claims supported by the source chunks. Add no new facts.\n"
    "2. Keep every citation exactly as written in the draft, in square brackets. Never "
    "shorten, alter or add a chunk ID.\n"
    f"3. If the draft is not supported by the chunks, respond exactly: {REFUSAL_MESSAGE}\n"
    "4. If policy_lookup_failed is true, do not answer from memory and do not invent any "
    "policy, error meaning, fix or deadline. Say plainly that documentation lookup is "
    "temporarily unavailable and that the question has been escalated for manual follow-up."
)


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

    raw = hybrid_search(DEFAULT_COLLECTION, query, top_n=TOP_K)
    chunks = [{**c, "score": c.get("rrf_score", 0.0)} for c in raw]
    if chunks and max(c["score"] for c in chunks) < MIN_SCORE_HYBRID:
        chunks = []
    return {"status": 200, "chunks": chunks}


_CODE_HINT = re.compile(r"\b(?:ERR|PAY|PLAN)-|\b\d{4}\b", re.I)


def run_triage_worker(question):
    triage = {"intent": "other", "mentioned_codes": [], "normalized_query": question}
    # Rewriting only helps when there is a code to normalize; otherwise it just drifts the wording.
    if not _CODE_HINT.search(question):
        return triage, _handoff("orchestrator_to_triage_worker", 0, 0, 0.0, "skipped_no_code_to_normalize")

    t0 = time.perf_counter()
    text, tok_in, tok_out = ask_llm(TRIAGE_SYSTEM_PROMPT, question)
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
    for attempt in range(1, POLICY_TOOL_MAX_ATTEMPTS + 1):
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
        handoffs.append(_handoff("policy_worker_search_tool", 0, 0, ms, f"attempt={attempt} status={result['status']} retrying={attempt < POLICY_TOOL_MAX_ATTEMPTS}"))

    if lookup_failed:
        return {"draft": "", "chunks": [], "lookup_failed": True, "attempts": attempts}, handoffs
    if not chunks:
        return {"draft": REFUSAL_MESSAGE, "chunks": [], "lookup_failed": False, "attempts": attempts}, handoffs

    t0 = time.perf_counter()
    draft, tok_in, tok_out = ask_llm(POLICY_SYSTEM_PROMPT, build_user_prompt(query, chunks))
    ms = (time.perf_counter() - t0) * 1000
    handoffs.append(_handoff("orchestrator_to_policy_worker", tok_in, tok_out, ms, f"chunks={len(chunks)}"))
    return {"draft": draft, "chunks": chunks, "lookup_failed": False, "attempts": attempts}, handoffs


def run_multi_agent(question, inject_failure=False):
    t_start = time.perf_counter()
    model = GROQ_MODEL if LLM_PROVIDER == "groq" else OLLAMA_MODEL
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
        final, tok_in, tok_out = ask_llm(SYNTHESIS_SYSTEM_PROMPT, user_msg)
        handoffs.append(_handoff("orchestrator_synthesis", tok_in, tok_out, (time.perf_counter() - t0) * 1000, "degraded_path"))
    elif not chunks or policy["draft"].strip() == REFUSAL_MESSAGE:
        final = REFUSAL_MESSAGE
        handoffs.append(_handoff("orchestrator_synthesis", 0, 0, 0.0, "skipped_no_llm_refusal_passthrough"))
    else:
        cited = extract_citations(policy["draft"])
        cited_chunks = [c for c in chunks if c["chunk_id"].lower() in cited] or chunks
        user_msg = (
            f"Question: {question}\n\npolicy_lookup_failed: false\n\n"
            f"Draft:\n{policy['draft']}\n\nSource chunks:\n\n{build_context(cited_chunks)}"
        )
        t0 = time.perf_counter()
        final, tok_in, tok_out = ask_llm(SYNTHESIS_SYSTEM_PROMPT, user_msg)
        handoffs.append(_handoff("orchestrator_synthesis", tok_in, tok_out, (time.perf_counter() - t0) * 1000, f"cited_chunks={len(cited_chunks)}"))
        if final.strip() == REFUSAL_MESSAGE:
            final = REFUSAL_MESSAGE
        else:
            citations_valid = validate_citations(extract_citations(final), retrieved_ids)
            if not citations_valid:
                final = REFUSAL_MESSAGE

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

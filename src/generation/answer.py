import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import re as _re

from src.catalog import settings
from src.config import DEFAULT_COLLECTION
from src.generation.cost import calculate_cost
from src.generation.citations import extract_citations, validate_citations
from src.generation.langfuse_client import get_langfuse
from src.generation.llm_client import LLM_PROVIDER, ask_llm, default_model
from src.generation.prompts import build_user_prompt, prompt_version, system_prompt
from src.generation.refusal import refusal_message
from src.retrieval.query_filter import is_query_relevant
from src.retrieval.search import search

_CITATION_BRACKET_RE = _re.compile(r"\[([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*--[A-Za-z0-9-]+--[A-Za-z0-9-]+)\]")

# Legacy Week 6 pages read this file. Writing it is opt-in (TRACE_JSONL_MIRROR=true); Langfuse is the trace store.
_TRACES_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "traces.jsonl"

logger = logging.getLogger(__name__)

# The prompt version recorded on traces follows the active catalog version of docs.system (see prompts.prompt_version).


@dataclass
class Answer:
    question: str
    retrieved_chunks: list[dict]
    raw_answer: str
    final_answer: str
    citations: set[str]
    citations_valid: bool
    retrieval_ms: float = field(default=0.0)
    generation_ms: float = field(default=0.0)
    retriever: str = field(default="hybrid-bm25-rrf")
    input_tokens: int = field(default=0)
    output_tokens: int = field(default=0)
    trace_id: str = field(default="")


def _langfuse_costs(model, input_tokens, output_tokens):
    cost = calculate_cost(model, input_tokens, output_tokens)
    return {
        "inputCost": cost["input_cost_usd"],
        "outputCost": cost["output_cost_usd"],
        "totalCost": cost["total_cost_usd"],
    }


def _write_trace(answer: "Answer", question: str, k: int, collection_name: str, trace_id: str | None = None,
                 user_email: str | None = None, lf_trace=None, lf=None, reason: str | None = None) -> None:
    """Finish a request: push the complete snapshot to Langfuse (the only trace store) and check alerts."""
    model = default_model()
    cost = calculate_cost(model, answer.input_tokens, answer.output_tokens)["total_cost_usd"]
    refused = answer.final_answer.startswith(("I don't have enough information to answer that", "I cannot answer that from the indexed help"))
    record = {
        "trace_id": trace_id or answer.trace_id or str(uuid4()),
        "user_email": user_email,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "original_query": question,
        "rewritten_query": None,
        "prompt_version": prompt_version(),
        "model": model,
        "temperature": 0.0,
        "retriever": answer.retriever,
        "top_k": k,
        "collection": collection_name,
        "retrieved_chunks": [
            {
                "chunk_id": c["chunk_id"],
                "document_id": c.get("article_id"),
                "score": c["score"],
                "rank": c["rank"],
            }
            for c in answer.retrieved_chunks
        ],
        "raw_output": answer.raw_answer,
        "final_answer": answer.final_answer,
        "citations": list(answer.citations),
        "citations_valid": answer.citations_valid,
        "retrieval_ms": round(answer.retrieval_ms, 2),
        "generation_ms": round(answer.generation_ms, 2),
        "total_ms": round(answer.retrieval_ms + answer.generation_ms, 2),
        "input_tokens": answer.input_tokens,
        "output_tokens": answer.output_tokens,
        "cost_usd": cost,
        "cost_by_stage": {"retrieval_usd": 0.0, "generation_usd": cost, "tools_usd": 0.0},
        "error": None,
    }
    answer.trace_id = record["trace_id"]
    logger.info(
        "trace=%s pv=%s retrieval_ms=%.1f generation_ms=%.1f in=%d out=%d cost_usd=%.8f citations_valid=%s",
        record["trace_id"], prompt_version(), answer.retrieval_ms, answer.generation_ms,
        answer.input_tokens, answer.output_tokens, cost, answer.citations_valid,
    )
    if lf_trace is not None:
        try:
            lf_trace.update(
                output={"final_answer": answer.final_answer, "reason": reason},
                metadata={
                    "prompt_version": prompt_version(),
                    "model": model,
                    "retriever": answer.retriever,
                    "collection": collection_name,
                    "top_k": k,
                    "temperature": 0.0,
                    "citations_valid": answer.citations_valid,
                    "citations": record["citations"],
                    "unverified": (not answer.citations_valid) and not refused,
                    "retrieved_chunks": record["retrieved_chunks"],
                    "retrieval_ms": record["retrieval_ms"],
                    "generation_ms": record["generation_ms"],
                    "total_ms": record["total_ms"],
                    "input_tokens": answer.input_tokens,
                    "output_tokens": answer.output_tokens,
                    "cost_usd": cost,
                },
            )
            if lf is not None:
                lf.flush()
        except Exception:
            logger.exception("failed to update the Langfuse trace")
    try:
        from src.observability.trace_store import remember
        remember(record)
    except Exception:
        logger.exception("failed to cache the trace summary")
    if os.getenv("TRACE_JSONL_MIRROR", "false").lower() == "true":
        try:
            with _TRACES_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            logger.exception("failed to write the legacy trace file")
    try:
        from src.observability.alerting import check_and_alert
        check_and_alert(record)
    except Exception:
        logger.exception("alerting failed")


def answer_question(
    question: str,
    collection_name: str = DEFAULT_COLLECTION,
    k: int | None = None,
    where: dict | None = None,
    use_hybrid: bool = True,
    user_email: str | None = None,
) -> Answer:
    k = settings.get("docs.top_k") if k is None else k
    trace_id = str(uuid4())
    retriever_label = "hybrid-bm25-rrf" if use_hybrid else "dense"
    model = default_model()
    lf = get_langfuse()

    trace = None
    if lf:
        try:
            trace = lf.trace(
                id=trace_id,
                name="answer_question",
                user_id=user_email,
                version=prompt_version(),
                tags=[f"prompt:{prompt_version()}"],
                input={"question": question},
                metadata={
                    "prompt_version": prompt_version(),
                    "collection": collection_name,
                    "retriever": retriever_label,
                    "top_k": k,
                    "model": model,
                },
            )
        except Exception:
            trace = None

    # ── Pre-retrieval query relevance gate ────────────────────────────────
    try:
        if not is_query_relevant(question, collection_name, settings.get("docs.min_query_relevance")):
            ans = Answer(
                question=question,
                retrieved_chunks=[],
                raw_answer=refusal_message(),
                final_answer=refusal_message(),
                citations=set(),
                citations_valid=False,
                retrieval_ms=0.0,
                generation_ms=0.0,
                retriever=retriever_label,
            )
            _write_trace(ans, question, k, collection_name, trace_id, user_email, trace, lf, "off_topic_query")
            return ans
    except Exception:
        pass  # if the gate fails, proceed to retrieval rather than blocking

    # ── Retrieval ──────────────────────────────────────────────────────────
    retrieval_span = (
        trace.span(
            name="retrieval",
            input={"query": question, "collection": collection_name, "use_hybrid": use_hybrid},
        )
        if trace
        else None
    )

    t0 = time.perf_counter()
    if use_hybrid:
        from src.retrieval.hybrid_search import hybrid_search
        raw_chunks = hybrid_search(collection_name, question, top_n=k)
        retrieved_chunks = [
            {**c, "score": c.get("rrf_score", 0.0)} for c in raw_chunks
        ]
    else:
        retrieved_chunks = search(collection_name, question, k=k, where=where)
    retrieval_ms = (time.perf_counter() - t0) * 1000

    # Drop all chunks if the best score falls below the relevance threshold.
    # This prevents the LLM from hallucinating answers for off-topic queries.
    if retrieved_chunks:
        threshold = settings.get("docs.min_score_hybrid") if use_hybrid else settings.get("docs.min_score_dense")
        best_score = max(c["score"] for c in retrieved_chunks)
        if best_score < threshold:
            retrieved_chunks = []

    if retrieval_span:
        retrieval_span.end(
            output={
                "chunk_ids": [c["chunk_id"] for c in retrieved_chunks],
                "count": len(retrieved_chunks),
            },
            metadata={"retrieval_ms": round(retrieval_ms, 2)},
        )

    retrieved_ids = {chunk["chunk_id"] for chunk in retrieved_chunks}

    if not retrieved_chunks:
        ans = Answer(
            question=question,
            retrieved_chunks=[],
            raw_answer=refusal_message(),
            final_answer=refusal_message(),
            citations=set(),
            citations_valid=False,
            retrieval_ms=retrieval_ms,
            generation_ms=0.0,
            retriever=retriever_label,
        )
        _write_trace(ans, question, k, collection_name, trace_id, user_email, trace, lf, "no_chunks_retrieved")
        return ans

    user_prompt = build_user_prompt(question, retrieved_chunks)

    # ── LLM generation ─────────────────────────────────────────────────────
    generation = (
        trace.generation(
            name="llm_call",
            model=model,
            input=[
                {"role": "system", "content": system_prompt()},
                {"role": "user", "content": user_prompt},
            ],
            metadata={"temperature": 0.0, "provider": LLM_PROVIDER},
        )
        if trace
        else None
    )

    t1 = time.perf_counter()
    raw_answer, input_tokens, output_tokens = ask_llm(system_prompt(), user_prompt)
    generation_ms = (time.perf_counter() - t1) * 1000

    if generation:
        generation.end(
            output=raw_answer,
            usage={
                "input": input_tokens,
                "output": output_tokens,
                "unit": "TOKENS",
                **_langfuse_costs(model, input_tokens, output_tokens),
            },
            metadata={"generation_ms": round(generation_ms, 2)},
        )

    if raw_answer.strip() == refusal_message():
        ans = Answer(
            question=question,
            retrieved_chunks=retrieved_chunks,
            raw_answer=raw_answer,
            final_answer=refusal_message(),
            citations=set(),
            citations_valid=False,
            retrieval_ms=retrieval_ms,
            generation_ms=generation_ms,
            retriever=retriever_label,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        _write_trace(ans, question, k, collection_name, trace_id, user_email, trace, lf, "llm_refused")
        return ans

    citations = extract_citations(raw_answer)
    citations_valid = validate_citations(citations, retrieved_ids)

    if citations_valid:
        final_answer = raw_answer
    elif not citations:
        # No citations at all -- keep the answer as-is (model answered without citing)
        final_answer = raw_answer
    else:
        # Some citations are invalid: strip the hallucinated ones and keep the rest.
        normalised_retrieved = {rid.lower() for rid in retrieved_ids}
        invalid_ids = citations - normalised_retrieved

        cleaned = raw_answer
        for inv_id in invalid_ids:
            cleaned = _CITATION_BRACKET_RE.sub(
                lambda m, bad=inv_id: "" if m.group(1).lower() == bad else m.group(0),
                cleaned,
            )
        remaining = extract_citations(cleaned)
        if remaining:
            final_answer = cleaned
            citations = remaining
            citations_valid = True
        else:
            # All citations were hallucinated -- return the refusal
            final_answer = refusal_message()

    ans = Answer(
        question=question,
        retrieved_chunks=retrieved_chunks,
        raw_answer=raw_answer,
        final_answer=final_answer,
        citations=citations,
        citations_valid=citations_valid,
        retrieval_ms=retrieval_ms,
        generation_ms=generation_ms,
        retriever=retriever_label,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


    _write_trace(ans, question, k, collection_name, trace_id, user_email, trace, lf, None)
    return ans

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.config import DEFAULT_COLLECTION, MIN_QUERY_RELEVANCE, MIN_SCORE_DENSE, MIN_SCORE_HYBRID, TOP_K
from src.generation.citations import extract_citations, validate_citations
from src.generation.langfuse_client import get_langfuse
from src.generation.llm_client import LLM_PROVIDER, GROQ_MODEL, OLLAMA_MODEL, ask_llm
from src.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from src.generation.refusal import REFUSAL_MESSAGE
from src.retrieval.query_filter import is_query_relevant
from src.retrieval.search import search

_TRACES_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "traces.jsonl"


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


def _write_trace(answer: "Answer", question: str, k: int, collection_name: str) -> None:
    model = GROQ_MODEL if LLM_PROVIDER == "groq" else OLLAMA_MODEL
    record = {
        "trace_id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "original_query": question,
        "rewritten_query": None,
        "prompt_version": "v1",
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
        "error": None,
    }
    try:
        with _TRACES_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def answer_question(
    question: str,
    collection_name: str = DEFAULT_COLLECTION,
    k: int = TOP_K,
    where: dict | None = None,
    use_hybrid: bool = True,
) -> Answer:
    retriever_label = "hybrid-bm25-rrf" if use_hybrid else "dense"
    model = GROQ_MODEL if LLM_PROVIDER == "groq" else OLLAMA_MODEL
    lf = get_langfuse()

    trace = None
    if lf:
        try:
            trace = lf.trace(
                name="answer_question",
                input={"question": question},
                metadata={
                    "collection": collection_name,
                    "retriever": retriever_label,
                    "top_k": k,
                    "model": model,
                },
            )
        except Exception:
            trace = None

    # ── Pre-retrieval relevance gate ───────────────────────────────────────
    # Embed the query and compare against the corpus centroid.  If the query
    # is too far from the indexed content, refuse immediately without touching
    # ChromaDB or BM25 at all.
    if not is_query_relevant(question, collection_name, MIN_QUERY_RELEVANCE):
        ans = Answer(
            question=question,
            retrieved_chunks=[],
            raw_answer=REFUSAL_MESSAGE,
            final_answer=REFUSAL_MESSAGE,
            citations=set(),
            citations_valid=False,
            retrieval_ms=0.0,
            generation_ms=0.0,
            retriever=retriever_label,
        )
        if trace:
            trace.update(
                output={"final_answer": REFUSAL_MESSAGE, "reason": "query_off_topic"},
                metadata={"citations_valid": False},
            )
            lf.flush()
        _write_trace(ans, question, k, collection_name)
        return ans

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
        threshold = MIN_SCORE_HYBRID if use_hybrid else MIN_SCORE_DENSE
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
            raw_answer=REFUSAL_MESSAGE,
            final_answer=REFUSAL_MESSAGE,
            citations=set(),
            citations_valid=False,
            retrieval_ms=retrieval_ms,
            generation_ms=0.0,
            retriever=retriever_label,
        )
        if trace:
            trace.update(
                output={"final_answer": REFUSAL_MESSAGE, "reason": "no_chunks_retrieved"},
                metadata={"citations_valid": False},
            )
            lf.flush()
        _write_trace(ans, question, k, collection_name)
        return ans

    user_prompt = build_user_prompt(question, retrieved_chunks)

    # ── LLM generation ─────────────────────────────────────────────────────
    generation = (
        trace.generation(
            name="llm_call",
            model=model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            metadata={"temperature": 0.0, "provider": LLM_PROVIDER},
        )
        if trace
        else None
    )

    t1 = time.perf_counter()
    raw_answer, input_tokens, output_tokens = ask_llm(SYSTEM_PROMPT, user_prompt)
    generation_ms = (time.perf_counter() - t1) * 1000

    if generation:
        generation.end(
            output=raw_answer,
            usage={
                "input": input_tokens,
                "output": output_tokens,
                "unit": "TOKENS",
            },
            metadata={"generation_ms": round(generation_ms, 2)},
        )

    if raw_answer.strip() == REFUSAL_MESSAGE:
        ans = Answer(
            question=question,
            retrieved_chunks=retrieved_chunks,
            raw_answer=raw_answer,
            final_answer=REFUSAL_MESSAGE,
            citations=set(),
            citations_valid=False,
            retrieval_ms=retrieval_ms,
            generation_ms=generation_ms,
            retriever=retriever_label,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        if trace:
            trace.update(
                output={"final_answer": REFUSAL_MESSAGE, "reason": "llm_refused"},
                metadata={"citations_valid": False, "input_tokens": input_tokens, "output_tokens": output_tokens},
            )
            lf.flush()
        _write_trace(ans, question, k, collection_name)
        return ans

    citations = extract_citations(raw_answer)
    citations_valid = validate_citations(citations, retrieved_ids)
    final_answer = raw_answer if citations_valid else REFUSAL_MESSAGE

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

    if trace:
        trace.update(
            output={"final_answer": final_answer},
            metadata={
                "citations_valid": citations_valid,
                "citations": list(citations),
                "retrieval_ms": round(retrieval_ms, 2),
                "generation_ms": round(generation_ms, 2),
                "total_ms": round(retrieval_ms + generation_ms, 2),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        )
        lf.flush()

    _write_trace(ans, question, k, collection_name)
    return ans

import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import re as _re

from api.models import AskRequest, AskResponse, ChunkResult, ReplayResult, TracePrompt, TraceRecord, TracesResponse

_CODE_RE = _re.compile(r"\b[A-Z]{2,}-[A-Z0-9]{2,}(?:-[A-Z0-9]+)+\b")


def _normalise(text: str) -> str:
    """Strip and normalise line endings for output comparison."""
    return text.strip().replace("\r\n", "\n").replace("\r", "\n")
_MULTI_PART_MARKERS = (" and ", " as well", " also ", "both ", " plus ", " additionally")
_SEMANTIC_STARTS = ("why ", "how does ", "how do ", "what happens ", "explain ",
                    "describe ", "what would ", "when does ", "when do ")


def _classify_query_type(question: str) -> str:
    q = question.lower()
    if question.count("?") > 1:
        return "multi-part"
    if any(m in q for m in _MULTI_PART_MARKERS) and "?" in question:
        return "multi-part"
    if _CODE_RE.search(question):
        return "exact keyword"
    if q.startswith(_SEMANTIC_STARTS):
        return "semantic"
    return "simple"
from src.generation.answer import answer_question
from src.generation.llm_client import LLMRequestError

_TRACES_PATH = Path(__file__).resolve().parent.parent / "evaluation" / "traces.jsonl"
_SAMPLE_PATH = Path(__file__).resolve().parent.parent / "evaluation" / "sample.jsonl"

app = FastAPI(title="Billing Support RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.post("/api/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    try:
        result = answer_question(request.question, use_hybrid=request.use_hybrid)
    except LLMRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    chunks = [
        ChunkResult(
            rank=c["rank"],
            chunk_id=c["chunk_id"],
            article_id=c.get("article_id"),
            section=c.get("section"),
            score=c["score"],
            text=c["text"],
        )
        for c in result.retrieved_chunks
    ]

    return AskResponse(
        answer=result.final_answer,
        chunks=chunks,
        retrieval_ms=round(result.retrieval_ms, 1),
        generation_ms=round(result.generation_ms, 1),
        total_ms=round(result.retrieval_ms + result.generation_ms, 1),
        citations_valid=result.citations_valid,
        retriever=result.retriever,
    )


@app.get("/api/traces", response_model=TracesResponse)
def get_traces(
    citations_valid: Optional[bool] = Query(default=None),
    retriever: Optional[str] = Query(default=None),
    error_only: bool = Query(default=False),
    question: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> TracesResponse:
    if not _TRACES_PATH.exists():
        return TracesResponse(traces=[], total=0, offset=offset, limit=limit)

    records: list[dict] = []
    with _TRACES_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if citations_valid is not None:
        records = [r for r in records if r.get("citations_valid") == citations_valid]
    if retriever is not None:
        records = [r for r in records if r.get("retriever") == retriever]
    if error_only:
        records = [r for r in records if not r.get("citations_valid") or r.get("error")]
    if question:
        q_lower = question.lower()
        records = [r for r in records if q_lower in r.get("question", "").lower()]

    total = len(records)
    page = records[offset : offset + limit]

    traces = []
    for r in page:
        try:
            if not r.get("query_type"):
                r["query_type"] = _classify_query_type(r.get("question", ""))
            traces.append(TraceRecord(**r))
        except Exception:
            continue
    return TracesResponse(traces=traces, total=total, offset=offset, limit=limit)


def _load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


@app.get("/api/traces/sample", response_model=list[TraceRecord])
def get_sample_traces() -> list[TraceRecord]:
    """Return the fixed 20-trace random sample (written by sample_traces.py)."""
    if not _SAMPLE_PATH.exists():
        return []
    records = _load_jsonl(_SAMPLE_PATH)
    result = []
    for r in records:
        try:
            if not r.get("query_type"):
                r["query_type"] = _classify_query_type(r.get("question", ""))
            result.append(TraceRecord(**r))
        except Exception:
            continue
    return result


@app.get("/api/traces/{trace_id}/prompt", response_model=TracePrompt)
def get_trace_prompt(trace_id: str) -> TracePrompt:
    """Return the system and user prompt that were sent to the LLM for this trace."""
    from src.generation.prompts import SYSTEM_PROMPT, build_user_prompt
    from src.retrieval.vector_store import get_collection

    trace: Optional[dict] = None
    for path in (_SAMPLE_PATH, _TRACES_PATH):
        if not path.exists():
            continue
        for rec in _load_jsonl(path):
            if rec.get("trace_id") == trace_id:
                trace = rec
                break
        if trace:
            break

    if trace is None:
        raise HTTPException(status_code=404, detail=f"trace_id '{trace_id}' not found")

    original_chunks = trace.get("retrieved_chunks", [])
    chunk_ids = [c["chunk_id"] for c in original_chunks]
    rank_by_id = {c["chunk_id"]: c.get("rank", i + 1) for i, c in enumerate(original_chunks)}

    prompt_chunks = []
    if chunk_ids:
        try:
            collection = get_collection(trace.get("collection", "billing_docs"))
            result = collection.get(ids=chunk_ids, include=["documents", "metadatas"])
            fetched = {}
            for cid, doc, meta in zip(result["ids"], result["documents"], result["metadatas"]):
                fetched[cid] = {
                    "chunk_id": cid,
                    "article_id": meta.get("article_id"),
                    "section": meta.get("section"),
                    "score": 0.0,
                    "rank": rank_by_id.get(cid, 1),
                    "text": doc,
                }
            for cid in chunk_ids:
                if cid in fetched:
                    prompt_chunks.append(fetched[cid])
        except Exception:
            pass

    user_prompt = build_user_prompt(trace["question"], prompt_chunks) if prompt_chunks else "(chunk text unavailable — ChromaDB unreachable)"

    return TracePrompt(
        trace_id=trace_id,
        query_type=_classify_query_type(trace.get("question", "")),
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )


@app.get("/api/traces/{trace_id}/replay", response_model=ReplayResult)
def replay_trace(trace_id: str) -> ReplayResult:
    """Replay a trace: fetch its chunks from ChromaDB and re-call the LLM."""
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

    from src.generation.citations import extract_citations, validate_citations
    from src.generation.llm_client import LLM_PROVIDER, GROQ_MODEL, OLLAMA_MODEL, ask_llm
    from src.generation.prompts import SYSTEM_PROMPT, build_user_prompt
    from src.retrieval.vector_store import get_collection

    # Find the trace (check sample first, then full file)
    trace: Optional[dict] = None
    for path in (_SAMPLE_PATH, _TRACES_PATH):
        if not path.exists():
            continue
        for rec in _load_jsonl(path):
            if rec.get("trace_id") == trace_id:
                trace = rec
                break
        if trace:
            break

    if trace is None:
        raise HTTPException(status_code=404, detail=f"trace_id '{trace_id}' not found")

    # Build rank lookup from stored trace so we can restore original order after ChromaDB fetch
    original_chunks = trace.get("retrieved_chunks", [])
    chunk_ids = [c["chunk_id"] for c in original_chunks]
    rank_by_id = {c["chunk_id"]: c.get("rank", i + 1) for i, c in enumerate(original_chunks)}

    chunks_available = False
    chunks_used = []

    if chunk_ids:
        try:
            collection = get_collection(trace["collection"])
            result = collection.get(ids=chunk_ids, include=["documents", "metadatas"])
            fetched = {}
            for cid, doc, meta in zip(result["ids"], result["documents"], result["metadatas"]):
                fetched[cid] = {
                    "chunk_id": cid,
                    "article_id": meta.get("article_id"),
                    "section": meta.get("section"),
                    "text": doc,
                }
            # Restore original rank order — ChromaDB.get() does not preserve input order
            for cid in chunk_ids:
                if cid in fetched:
                    chunks_used.append(fetched[cid])
            chunks_available = bool(chunks_used)
        except Exception:
            pass

    replayed_raw = ""
    replayed_citations: set[str] = set()
    replayed_citations_valid = False
    in_tok = 0
    out_tok = 0

    original_model = trace.get("model", "unknown")
    # Default replay_model to env default; overwritten below after the actual call
    env_default_model = GROQ_MODEL if LLM_PROVIDER == "groq" else OLLAMA_MODEL
    replay_model = original_model  # we will try to use the stored model

    if chunks_available and chunks_used:
        # Build prompt chunks with original rank — same structure as answer.py
        prompt_chunks = [
            {
                "chunk_id": c["chunk_id"],
                "article_id": c["article_id"],
                "section": c["section"],
                "score": 0.0,
                "rank": rank_by_id.get(c["chunk_id"], i + 1),
                "text": c["text"],
            }
            for i, c in enumerate(chunks_used)
        ]
        user_prompt = build_user_prompt(trace["question"], prompt_chunks)
        try:
            # Pass original_model so the replay uses exactly the same model as the trace
            replayed_raw, in_tok, out_tok = ask_llm(SYSTEM_PROMPT, user_prompt, model=original_model)
            replay_model = original_model
        except LLMRequestError:
            # Stored model unavailable — fall back to env default and note the switch
            replayed_raw, in_tok, out_tok = ask_llm(SYSTEM_PROMPT, user_prompt)
            replay_model = env_default_model
        retrieved_ids = {c["chunk_id"] for c in chunks_used}
        replayed_citations = extract_citations(replayed_raw)
        replayed_citations_valid = validate_citations(replayed_citations, retrieved_ids)

    original_citations = set(trace.get("citations", []))
    original_citations_valid = trace.get("citations_valid", False)

    return ReplayResult(
        trace_id=trace_id,
        question=trace["question"],
        original_model=original_model,
        replay_model=replay_model,
        model_matched=(original_model == replay_model),
        original_raw_output=trace["raw_output"],
        original_citations=sorted(original_citations),
        original_citations_valid=original_citations_valid,
        replayed_raw_output=replayed_raw,
        replayed_citations=sorted(replayed_citations),
        replayed_citations_valid=replayed_citations_valid,
        chunks_used=chunks_used,
        chunks_available=chunks_available,
        replayed_input_tokens=in_tok,
        replayed_output_tokens=out_tok,
        outputs_match=(_normalise(trace["raw_output"]) == _normalise(replayed_raw)),
    )

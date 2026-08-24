import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from api.models import AskRequest, AskResponse, ChunkResult, ReplayResult, TraceRecord, TracesResponse
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
            result.append(TraceRecord(**r))
        except Exception:
            continue
    return result


@app.get("/api/traces/{trace_id}/replay", response_model=ReplayResult)
def replay_trace(trace_id: str) -> ReplayResult:
    """Replay a trace: fetch its chunks from ChromaDB and re-call the LLM."""
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

    from src.generation.citations import extract_citations, validate_citations
    from src.generation.llm_client import ask_llm
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

    chunk_ids = [c["chunk_id"] for c in trace.get("retrieved_chunks", [])]
    chunks_available = False
    chunks_used = []

    if chunk_ids:
        try:
            collection = get_collection(trace["collection"])
            result = collection.get(ids=chunk_ids, include=["documents", "metadatas"])
            for cid, doc, meta in zip(result["ids"], result["documents"], result["metadatas"]):
                chunks_used.append({
                    "chunk_id": cid,
                    "article_id": meta.get("article_id"),
                    "section": meta.get("section"),
                    "text": doc,
                })
            chunks_available = True
        except Exception:
            pass

    replayed_raw = ""
    replayed_citations: set[str] = set()
    replayed_citations_valid = False
    in_tok = 0
    out_tok = 0

    if chunks_available and chunks_used:
        # Build chunks in the format expected by build_user_prompt
        prompt_chunks = [
            {
                "chunk_id": c["chunk_id"],
                "article_id": c["article_id"],
                "section": c["section"],
                "score": 0.0,
                "rank": i + 1,
                "text": c["text"],
            }
            for i, c in enumerate(chunks_used)
        ]
        user_prompt = build_user_prompt(trace["question"], prompt_chunks)
        replayed_raw, in_tok, out_tok = ask_llm(SYSTEM_PROMPT, user_prompt)
        retrieved_ids = {c["chunk_id"] for c in chunks_used}
        replayed_citations = extract_citations(replayed_raw)
        replayed_citations_valid = validate_citations(replayed_citations, retrieved_ids)

    original_citations = set(trace.get("citations", []))
    original_citations_valid = trace.get("citations_valid", False)

    return ReplayResult(
        trace_id=trace_id,
        question=trace["question"],
        model=trace["model"],
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
        outputs_match=(trace["raw_output"].strip() == replayed_raw.strip()),
    )

"""Billing Support RAG API — FastAPI application entry point."""

import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import re as _re

# ---------------------------------------------------------------------------
# Logging — structured, to stdout
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("api")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
_CODE_RE = _re.compile(r"\b[A-Z]{2,}-[A-Z0-9]{2,}(?:-[A-Z0-9]+)+\b")
_MULTI_PART_MARKERS = (" and ", " as well", " also ", "both ", " plus ", " additionally")
_SEMANTIC_STARTS = ("why ", "how does ", "how do ", "what happens ", "explain ",
                    "describe ", "what would ", "when does ", "when do ")


def _normalise(text: str) -> str:
    return text.strip().replace("\r\n", "\n").replace("\r", "\n")


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


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_TRACES_PATH = Path(__file__).resolve().parent.parent / "evaluation" / "traces.jsonl"
_SAMPLE_PATH = Path(__file__).resolve().parent.parent / "evaluation" / "sample.jsonl"
_ARTICLES_DIR = Path(__file__).resolve().parent.parent / "data" / "billing_articles"

# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    from api.database import init_db
    log.info("Initialising database…")
    init_db()
    log.info("Database ready")

    from src.generation.langfuse_client import get_langfuse
    lf = get_langfuse()
    log.info("LangFuse: %s", "enabled" if lf else "disabled (check .env keys)")

    yield
    log.info("Shutdown complete")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Billing Support RAG API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
from api.race_router import router as race_router
from api.agent_router import router as agent_router
from api.auth import router as auth_router, get_current_user, require_admin
from api.admin_router import router as admin_router
from api.trajectory_router import router as trajectory_router

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(race_router)
app.include_router(agent_router)
app.include_router(trajectory_router)

# ---------------------------------------------------------------------------
# CORS  —  restrict to configured origins only
# ---------------------------------------------------------------------------
from api.config import ALLOWED_ORIGINS, MAX_UPLOAD_BYTES

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization"],
    allow_credentials=True,
)

# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def _log_requests(request: Request, call_next):
    response = await call_next(request)
    log.info("%s %s %s", request.method, request.url.path, response.status_code)
    return response

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
from api.models import (
    AskRequest, AskResponse, ChunkResult,
    ReplayResult, TracePrompt, TraceRecord, TracesResponse, UploadResponse,
)

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok"}

# ---------------------------------------------------------------------------
# RAG ask endpoint (authenticated)
# ---------------------------------------------------------------------------

@app.post("/api/ask", response_model=AskResponse)
def ask(request: AskRequest, _user=Depends(get_current_user)) -> AskResponse:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    from src.generation.answer import answer_question
    from src.generation.llm_client import LLMRequestError

    try:
        result = answer_question(request.question, use_hybrid=request.use_hybrid)
    except LLMRequestError as exc:
        log.error("LLM error on ask: %s", exc)
        raise HTTPException(status_code=502, detail="LLM service unavailable — please retry") from exc

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

# ---------------------------------------------------------------------------
# Document upload (admin only, size-limited)
# ---------------------------------------------------------------------------
_ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".md", ".txt", ".docx", ".xlsx", ".xls"}


@app.post("/api/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    _admin=Depends(require_admin),
) -> UploadResponse:
    import shutil
    from src.config import DEFAULT_COLLECTION
    from src.ingestion.ingest_document import ingest_file

    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(_ALLOWED_UPLOAD_EXTENSIONS))}",
        )

    # Stream to a temp buffer and enforce size limit
    _ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    dest = _ARTICLES_DIR / filename
    bytes_written = 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(64 * 1024):
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_BYTES:
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large — maximum is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
                    )
                out.write(chunk)
    finally:
        await file.close()

    try:
        chunk_count = ingest_file(dest, DEFAULT_COLLECTION)
    except Exception as exc:
        dest.unlink(missing_ok=True)
        log.error("Ingestion failed for %s: %s", filename, exc)
        raise HTTPException(status_code=422, detail="Failed to process document") from exc

    log.info("Ingested %s — %d chunks", filename, chunk_count)
    return UploadResponse(
        filename=filename,
        chunks_indexed=chunk_count,
        collection=DEFAULT_COLLECTION,
        status="success",
    )

# ---------------------------------------------------------------------------
# Traces (authenticated)
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        log.warning("Skipping malformed JSONL line in %s", path.name)
    except FileNotFoundError:
        pass
    return records


@app.get("/api/traces", response_model=TracesResponse)
def get_traces(
    citations_valid: Optional[bool] = Query(default=None),
    retriever: Optional[str] = Query(default=None),
    error_only: bool = Query(default=False),
    question: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _user=Depends(get_current_user),
) -> TracesResponse:
    records = _load_jsonl(_TRACES_PATH)

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
    traces = []
    for r in records[offset: offset + limit]:
        try:
            if not r.get("query_type"):
                r["query_type"] = _classify_query_type(r.get("question", ""))
            traces.append(TraceRecord(**r))
        except Exception:
            log.debug("Skipping undecodable trace record")

    return TracesResponse(traces=traces, total=total, offset=offset, limit=limit)


@app.get("/api/traces/sample", response_model=list[TraceRecord])
def get_sample_traces(_user=Depends(get_current_user)) -> list[TraceRecord]:
    records = _load_jsonl(_SAMPLE_PATH)
    result = []
    for r in records:
        try:
            if not r.get("query_type"):
                r["query_type"] = _classify_query_type(r.get("question", ""))
            result.append(TraceRecord(**r))
        except Exception:
            pass
    return result


@app.get("/api/traces/{trace_id}/prompt", response_model=TracePrompt)
def get_trace_prompt(trace_id: str, _user=Depends(get_current_user)) -> TracePrompt:
    from src.generation.prompts import SYSTEM_PROMPT, build_user_prompt
    from src.retrieval.vector_store import get_collection

    trace: Optional[dict] = None
    for path in (_SAMPLE_PATH, _TRACES_PATH):
        for rec in _load_jsonl(path):
            if rec.get("trace_id") == trace_id:
                trace = rec
                break
        if trace:
            break

    if trace is None:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")

    original_chunks = trace.get("retrieved_chunks", [])
    chunk_ids = [c["chunk_id"] for c in original_chunks]
    rank_by_id = {c["chunk_id"]: c.get("rank", i + 1) for i, c in enumerate(original_chunks)}

    prompt_chunks = []
    if chunk_ids:
        try:
            collection = get_collection(trace.get("collection", "billing_docs"))
            result = collection.get(ids=chunk_ids, include=["documents", "metadatas"])
            fetched = {
                cid: {"chunk_id": cid, "article_id": meta.get("article_id"),
                      "section": meta.get("section"), "score": 0.0,
                      "rank": rank_by_id.get(cid, 1), "text": doc}
                for cid, doc, meta in zip(result["ids"], result["documents"], result["metadatas"])
            }
            prompt_chunks = [fetched[cid] for cid in chunk_ids if cid in fetched]
        except Exception as exc:
            log.warning("ChromaDB unavailable for trace prompt: %s", exc)

    user_prompt = (
        build_user_prompt(trace["question"], prompt_chunks)
        if prompt_chunks else "(chunk text unavailable — ChromaDB unreachable)"
    )
    return TracePrompt(
        trace_id=trace_id,
        query_type=_classify_query_type(trace.get("question", "")),
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )


@app.get("/api/traces/{trace_id}/replay", response_model=ReplayResult)
def replay_trace(trace_id: str, _user=Depends(get_current_user)) -> ReplayResult:
    from src.generation.citations import extract_citations, validate_citations
    from src.generation.llm_client import LLM_PROVIDER, GROQ_MODEL, OLLAMA_MODEL, LLMRequestError, ask_llm
    from src.generation.prompts import SYSTEM_PROMPT, build_user_prompt
    from src.retrieval.vector_store import get_collection

    trace: Optional[dict] = None
    for path in (_SAMPLE_PATH, _TRACES_PATH):
        for rec in _load_jsonl(path):
            if rec.get("trace_id") == trace_id:
                trace = rec
                break
        if trace:
            break

    if trace is None:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")

    original_chunks = trace.get("retrieved_chunks", [])
    chunk_ids = [c["chunk_id"] for c in original_chunks]
    rank_by_id = {c["chunk_id"]: c.get("rank", i + 1) for i, c in enumerate(original_chunks)}

    chunks_used: list[dict] = []
    if chunk_ids:
        try:
            collection = get_collection(trace["collection"])
            result = collection.get(ids=chunk_ids, include=["documents", "metadatas"])
            fetched = {
                cid: {"chunk_id": cid, "article_id": meta.get("article_id"),
                      "section": meta.get("section"), "text": doc}
                for cid, doc, meta in zip(result["ids"], result["documents"], result["metadatas"])
            }
            chunks_used = [fetched[cid] for cid in chunk_ids if cid in fetched]
        except Exception as exc:
            log.warning("ChromaDB unavailable for replay: %s", exc)

    replayed_raw = ""
    replayed_citations: set[str] = set()
    replayed_citations_valid = False
    in_tok = out_tok = 0
    original_model = trace.get("model", "unknown")
    env_default = GROQ_MODEL if LLM_PROVIDER == "groq" else OLLAMA_MODEL
    replay_model = original_model

    if chunks_used:
        prompt_chunks = [
            {**c, "score": 0.0, "rank": rank_by_id.get(c["chunk_id"], i + 1)}
            for i, c in enumerate(chunks_used)
        ]
        user_prompt = build_user_prompt(trace["question"], prompt_chunks)
        try:
            replayed_raw, in_tok, out_tok = ask_llm(SYSTEM_PROMPT, user_prompt, model=original_model)
        except LLMRequestError:
            replayed_raw, in_tok, out_tok = ask_llm(SYSTEM_PROMPT, user_prompt)
            replay_model = env_default
        retrieved_ids = {c["chunk_id"] for c in chunks_used}
        replayed_citations = extract_citations(replayed_raw)
        replayed_citations_valid = validate_citations(replayed_citations, retrieved_ids)

    return ReplayResult(
        trace_id=trace_id,
        question=trace["question"],
        original_model=original_model,
        replay_model=replay_model,
        model_matched=(original_model == replay_model),
        original_raw_output=trace["raw_output"],
        original_citations=sorted(set(trace.get("citations", []))),
        original_citations_valid=trace.get("citations_valid", False),
        replayed_raw_output=replayed_raw,
        replayed_citations=sorted(replayed_citations),
        replayed_citations_valid=replayed_citations_valid,
        chunks_used=chunks_used,
        chunks_available=bool(chunks_used),
        replayed_input_tokens=in_tok,
        replayed_output_tokens=out_tok,
        outputs_match=(_normalise(trace["raw_output"]) == _normalise(replayed_raw)),
    )

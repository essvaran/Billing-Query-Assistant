"""Billing Support RAG API — FastAPI application entry point."""

import json
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

import re as _re

# ---------------------------------------------------------------------------
# Logging — structured, to stdout
# ---------------------------------------------------------------------------
class _JsonFormatter(logging.Formatter):
    """One JSON object per line, so a log shipper can index fields instead of parsing text."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "level": record.levelname,
                 "logger": record.name, "msg": record.getMessage()}
        for key in ("request_id", "method", "path", "status", "ms"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def _configure_logging() -> None:
    """JSON lines in production (or LOG_FORMAT=json), readable text in development."""
    import os
    default = "json" if os.getenv("APP_ENV", "").strip().lower() == "production" else "text"
    handler = logging.StreamHandler()
    if os.getenv("LOG_FORMAT", default).strip().lower() == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s", "%Y-%m-%dT%H:%M:%S"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


_configure_logging()
log = logging.getLogger("api")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
_CODE_RE = _re.compile(r"\b[A-Z]{2,}-[A-Z0-9]{2,}(?:-[A-Z0-9]+)+\b")


def _markers(query_type: str) -> tuple[str, ...]:
    """Words that mark a Docs query type (catalog list query_type, field markers)."""
    from src.catalog import ref
    return tuple(ref.meta("query_type", query_type, "markers", []) or [])


def _normalise(text: str) -> str:
    return text.strip().replace("\r\n", "\n").replace("\r", "\n")


def _classify_query_type(question: str) -> str:
    q = question.lower()
    if question.count("?") > 1:
        return "multi-part"
    if any(m in q for m in _markers("multi-part")) and "?" in question:
        return "multi-part"
    if _CODE_RE.search(question):
        return "exact keyword"
    if q.startswith(_markers("semantic")):
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
    # Configuration first: in production a bad setting stops the API with a readable message instead of failing
    # later on a customer's ticket. In development the same findings are logged as warnings.
    from tier1 import preflight
    problems = preflight.check_env()
    for p in problems:
        log.warning("config %s %s: %s Fix: %s", p.level.upper(), p.key, p.message, p.fix)
    errors = [p for p in problems if p.level == "error"]
    if errors and preflight.is_production():
        raise SystemExit("Refusing to start in production: " + "; ".join(f"{p.key}: {p.fix}" for p in errors))

    from api.database import init_db
    log.info("Initialising database")
    init_db()
    log.info("Database ready")

    # Registers the span sink and the customer-name redaction provider in THIS process too, so names typed into
    # a ticket are scrubbed from API-side traces and logs, not only in the CLI and MCP server processes.
    from tier1 import tracing_store
    tracing_store.install()

    # Answer jobs run in threads of this process, so any job still 'running' lost its worker at the last stop.
    try:
        from tier1 import db as tier1_db, store as tier1_store
        tier1_db.init_db()
        ended = tier1_store.fail_interrupted_jobs()
        if ended:
            log.warning("Marked %d interrupted answer job(s) as failed", ended)
    except Exception as exc:                     # the ticket database is optional until the first ticket
        log.warning("Could not check for interrupted jobs: %s", type(exc).__name__)

    from src.generation.langfuse_client import get_langfuse
    lf = get_langfuse()
    log.info("LangFuse: %s", "enabled" if lf else "disabled (check .env keys)")

    yield
    log.info("Shutdown complete")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
from api.limiter import limiter, user_or_ip
import api.config  # noqa: F401,E402  loads .env before APP_ENV is read below
from tier1.preflight import is_production as _is_production

# The interactive API docs describe every endpoint, admin ones included, so they are off in production.
_DOCS = not _is_production()
app = FastAPI(
    title="Billing Support RAG API",
    version="1.0.0",
    docs_url="/api/docs" if _DOCS else None,
    redoc_url="/api/redoc" if _DOCS else None,
    openapi_url="/api/openapi.json" if _DOCS else None,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
from api.race_router import router as race_router
from api.agent_router import router as agent_router
from api.auth import router as auth_router, get_current_user, require_admin
from api.admin_router import router as admin_router
from api.account_router import router as account_router
from api.admin_billing_router import router as admin_billing_router
from api.trajectory_router import router as trajectory_router
from api.multiagent_router import router as multiagent_router
from api.tier1_router import router as tier1_router
from api.observability_router import router as observability_router
from api.feedback_router import router as feedback_router
from api.help_router import router as help_router
from api.catalog_router import router as catalog_router
from api.tier1_admin_router import router as tier1_admin_router
from api.eval_admin_router import router as eval_admin_router
from api.chat_router import router as chat_router

app.include_router(auth_router)
app.include_router(observability_router)
app.include_router(feedback_router)
app.include_router(admin_router)
app.include_router(account_router)
app.include_router(admin_billing_router)
app.include_router(race_router)
app.include_router(agent_router)
app.include_router(trajectory_router)
app.include_router(multiagent_router)
app.include_router(tier1_router)
app.include_router(help_router)
app.include_router(catalog_router)
app.include_router(tier1_admin_router)
app.include_router(eval_admin_router)
app.include_router(chat_router)

# ---------------------------------------------------------------------------
# CORS  —  restrict to configured origins only
# ---------------------------------------------------------------------------
from api.config import ALLOWED_ORIGINS, MAX_UPLOAD_BYTES

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
    allow_credentials=False,          # the session is a bearer token, never a cookie
)

# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------

_REQUEST_ID = _re.compile(r"^[A-Za-z0-9-]{8,64}$")


@app.middleware("http")
async def _log_requests(request: Request, call_next):
    """Every response carries X-Request-ID (the caller's, when it sent a sane one) and one access-log line
    with the same id, so a user quoting the id from an error message leads straight to the log line.
    An unhandled error becomes {detail, request_id} with no traceback in the body."""
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if _REQUEST_ID.match(incoming) else uuid.uuid4().hex
    request.state.request_id = request_id
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("Unhandled error", extra={"request_id": request_id, "method": request.method,
                                                "path": request.url.path})
        response = JSONResponse({"detail": "Internal error", "request_id": request_id}, status_code=500)
    ms = round((time.perf_counter() - start) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    log.info("%s %s %s %sms", request.method, request.url.path, response.status_code, ms,
             extra={"request_id": request_id, "method": request.method, "path": request.url.path,
                    "status": response.status_code, "ms": ms})
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
    """Liveness: the process is up. Use /api/ready to know whether it can answer tickets."""
    return {"status": "ok"}


@app.get("/api/ready", tags=["meta"])
def ready(request: Request):
    """Readiness: configuration valid, databases open, search index built. 503 when not ready.
    Checks only local state (no model call, no writes), so a load balancer can poll it cheaply. In production
    the list of problems (which secrets are weak or missing) goes only to an admin; everyone else gets the status."""
    from tier1 import db as tier1_db, preflight
    problems = [p for p in preflight.check_env() + preflight.check_data() if p.level == "error"]
    try:
        from api.database import get_db
        with get_db() as conn:
            conn.execute("SELECT 1")
        if Path(tier1_db.DB_PATH).exists():
            with tier1_db.get_conn() as conn:
                conn.execute("SELECT 1")
    except Exception as exc:
        problems.append(preflight.Problem("error", "database", f"A database could not be opened ({type(exc).__name__}).",
                                          "Check that the data/ folder is writable."))
    body = {"status": "ready" if not problems else "not_ready"}
    if not preflight.is_production() or _is_admin_request(request):
        body["env"] = preflight.app_env()
        body["problems"] = [{"key": p.key, "message": p.message, "fix": p.fix} for p in problems]
    return JSONResponse(body, status_code=200 if not problems else 503)


def _is_admin_request(request: Request) -> bool:
    from fastapi.security import HTTPAuthorizationCredentials
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return False
    try:
        user = get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=header[7:]))
    except HTTPException:
        return False
    return user.role == "admin"

# ---------------------------------------------------------------------------
# RAG ask endpoint (authenticated)
# ---------------------------------------------------------------------------

@app.post("/api/ask", response_model=AskResponse)
@limiter.limit("10/minute")
def ask(body: AskRequest, request: Request, _user=Depends(get_current_user)) -> AskResponse:
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    from src.generation.answer import answer_question
    from src.generation.llm_client import LLMRequestError

    try:
        result = answer_question(body.question, use_hybrid=body.use_hybrid, user_email=_user.email)
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
        trace_id=result.trace_id or None,
    )

# ---------------------------------------------------------------------------
# Document upload (admin only, size-limited)
# ---------------------------------------------------------------------------


def _allowed_upload_extensions() -> set[str]:
    """Active catalog list upload_extension, limited to the types the ingestion code has a loader for."""
    from src.catalog import ref
    from src.ingestion.ingest_document import SUPPORTED_EXTENSIONS
    return set(ref.codes("upload_extension")) & set(SUPPORTED_EXTENSIONS)


@app.post("/api/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    _admin=Depends(require_admin),
) -> UploadResponse:
    import shutil
    from src.config import DEFAULT_COLLECTION
    from src.ingestion.ingest_document import ingest_file

    # Only the last path part of the client's name is used, so "../../api/x.py" cannot write outside the folder.
    filename = Path((file.filename or "").replace("\\", "/")).name.strip() or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in _allowed_upload_extensions():
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(_allowed_upload_extensions()))}",
        )

    # Stream to a temp buffer and enforce size limit
    _ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    base = _ARTICLES_DIR.resolve()
    dest = (base / filename).resolve()
    if dest.parent != base:
        raise HTTPException(status_code=400, detail="Invalid file name")
    if dest.exists():
        raise HTTPException(status_code=409,
                            detail=f"An article named '{filename}' already exists. Rename the file or delete the old one first.")
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
        chunk_count = await run_in_threadpool(ingest_file, dest, DEFAULT_COLLECTION)
    except Exception as exc:
        dest.unlink(missing_ok=True)
        log.exception("Ingestion failed for %s", filename)
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=422, detail=f"Failed to process document: {exc}") from exc
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
    _user=Depends(require_admin),
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


@app.get("/api/traces/sample/meta")
def get_sample_meta(_user=Depends(require_admin)) -> dict:
    """How the Docs trace sample was drawn (settings docs.sample_seed and docs.sample_size) and how many rows it has."""
    from src.catalog import settings
    return {"seed": settings.get("docs.sample_seed"), "size": settings.get("docs.sample_size"), "n": len(_load_jsonl(_SAMPLE_PATH))}


@app.get("/api/traces/sample/taxonomy")
def get_sample_taxonomy(_user=Depends(require_admin)) -> dict:
    """Failed sample traces with their failure mode (catalog list sample_failure_mode), classified on the server."""
    import re as _re2
    from src.generation.refusal import is_refusal
    records = _load_jsonl(_SAMPLE_PATH)
    failed = [r for r in records if not r.get("citations_valid")]
    dash = _re2.compile("HC-BILL-\\d+[\u2013\u2014]")
    rows = []
    for r in failed:
        raw = r.get("raw_output") or r.get("final_answer") or ""
        mode = "Corpus Gap / False Refusal" if is_refusal(raw) else "Citation Character Error" if dash.search(raw) else "Citation Abbreviation"
        rows.append({"trace_id": r.get("trace_id"), "question": r.get("question", ""), "mode": mode})
    return {"total": len(records), "failed": len(rows), "rows": rows}


@app.get("/api/traces/sample", response_model=list[TraceRecord])
def get_sample_traces(_user=Depends(require_admin)) -> list[TraceRecord]:
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
def get_trace_prompt(trace_id: str, _user=Depends(require_admin)) -> TracePrompt:
    from src.generation.prompts import build_user_prompt, system_prompt
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
        system_prompt=system_prompt(),
        user_prompt=user_prompt,
    )


@app.get("/api/traces/{trace_id}/replay", response_model=ReplayResult)
@limiter.limit("10/minute", key_func=user_or_ip)
def replay_trace(request: Request, trace_id: str, _user=Depends(require_admin)) -> ReplayResult:
    from src.generation.citations import extract_citations, validate_citations
    from src.generation.llm_client import LLMRequestError, ask_llm, default_model
    from src.generation.prompts import build_user_prompt, system_prompt
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
    env_default = default_model()
    replay_model = original_model

    if chunks_used:
        prompt_chunks = [
            {**c, "score": 0.0, "rank": rank_by_id.get(c["chunk_id"], i + 1)}
            for i, c in enumerate(chunks_used)
        ]
        user_prompt = build_user_prompt(trace["question"], prompt_chunks)
        try:
            try:
                replayed_raw, in_tok, out_tok = ask_llm(system_prompt(), user_prompt, model=original_model)
            except LLMRequestError:
                replayed_raw, in_tok, out_tok = ask_llm(system_prompt(), user_prompt)
                replay_model = env_default
        except LLMRequestError as exc:
            log.error("Replay of %s failed: %s", trace_id, exc)
            raise HTTPException(status_code=502,
                                detail="The model service is unavailable. Try the replay again later.") from exc
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

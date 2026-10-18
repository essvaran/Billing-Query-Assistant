"""Observability API: trace search, cost stats, alerts, support drills, feedback and eval history.

Every route requires an admin JWT. Traces are read from Langfuse (the only trace store); alerts, drills,
feedback and eval history live in SQLite.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import UserOut, require_admin
from api.database import get_db
from src.observability import trace_store
from src.observability.stats import group_stats, percentile
from src.observability.trace_store import TraceStoreError

log = logging.getLogger("api.observability")
router = APIRouter(prefix="/api/obs", tags=["observability"], dependencies=[Depends(require_admin)])



def _setting(key: str):
    from src.catalog import settings
    return settings.get(key)


# ------------------------------------------------------------------ helpers

def _utc_iso(value, name):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{name} must be an ISO 8601 timestamp")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _env_float(name, default):
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


def _store_error(exc):
    return HTTPException(status_code=exc.status, detail=exc.message)


def _summary(item):
    return {
        "trace_id": item["trace_id"],
        "timestamp": item["timestamp"],
        "question": item["question"],
        "answer_preview": (item["final_answer"] or "")[:220],
        "prompt_version": item["prompt_version"],
        "model": item["model"],
        "user_email": item["user_email"],
        "citations_valid": item["citations_valid"],
        "unverified": bool(item["unverified"]),
        "is_refusal": item["is_refusal"],
        "total_ms": item["total_ms"],
        "cost_usd": item["cost_usd"],
        "input_tokens": item["input_tokens"],
        "output_tokens": item["output_tokens"],
        "error": item["error"],
    }


# ------------------------------------------------------------------ Langfuse and feedback helpers

def _langfuse_host():
    from src.generation import langfuse_client

    return langfuse_client.host() if langfuse_client.get_langfuse() else None


def _count_new_down():
    with get_db() as conn:
        return conn.execute("SELECT COUNT(*) FROM feedback WHERE rating='down' AND status='new'").fetchone()[0]


def _feedback_row(row):
    from src.observability.feedback import reasons

    item = dict(row)
    item["reason_label"] = reasons().get(item.get("reason_code"), item.get("reason_code"))
    return item


# ------------------------------------------------------------------ meta

@router.get("/meta")
def meta():
    from src.observability.alerting import is_enabled

    try:
        from src.generation.prompts import prompt_version
        PROMPT_VERSION = prompt_version()
    except Exception:
        PROMPT_VERSION = "unknown"
    return {
        "prompt_version": PROMPT_VERSION,
        "demo_tools_enabled": os.getenv("OBS_DEMO_TOOLS", "false").lower() == "true",
        "alerts_enabled": is_enabled(),
        "drill_bar_seconds": _setting("alerts.drill_bar_seconds"),
        "drill_complaint": (_setting("demo.incident") or {}).get("complaint", ""),
        "tenx_baseline_rpm": _setting("capacity.tenx_baseline_rpm"),
        "tenx_multiplier": _setting("capacity.tenx_multiplier"),
        "langfuse_url": _langfuse_host(),
        "langfuse_configured": trace_store.configured(),
        "feedback_new_down": _count_new_down(),
    }


# ------------------------------------------------------------------ traces

@router.get("/traces")
def list_traces(
    after: Optional[str] = Query(default=None),
    before: Optional[str] = Query(default=None),
    keyword: Optional[str] = Query(default=None, max_length=200),
    prompt_version: Optional[str] = Query(default=None, max_length=50),
    cost_above: Optional[float] = Query(default=None, ge=0),
    unverified: bool = Query(default=False),
    errors_only: bool = Query(default=False),
    user: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    filters = {
        "after": _utc_iso(after, "after") if after else None,
        "before": _utc_iso(before, "before") if before else None,
        "keyword": keyword,
        "prompt_version": prompt_version,
        "cost_above": cost_above,
        "unverified": unverified,
        "errors_only": errors_only,
        "user": user,
    }
    try:
        result = trace_store.search(filters, limit, offset)
    except TraceStoreError as exc:
        raise _store_error(exc)
    return {
        "total": result["total"], "limit": limit, "offset": offset,
        "items": [_summary(i) for i in result["items"]],
        "source": "langfuse", "scanned": result["scanned"], "truncated": result["truncated"],
    }


@router.get("/traces/{trace_id}")
def get_trace(trace_id: str):
    try:
        item = trace_store.get_trace(trace_id)
    except TraceStoreError as exc:
        raise _store_error(exc)
    if item is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    from src.observability.eval_runner import load_cases

    with get_db() as conn:
        feedback_rows = [_feedback_row(r) for r in conn.execute(
            "SELECT * FROM feedback WHERE trace_id = ? ORDER BY updated_at DESC", (trace_id,))]
    linked = next((c["case_id"] for c in load_cases() if c.get("regression_trace_id") == trace_id), None)
    chunks = item["retrieved_chunks"]
    cost = item["cost_usd"]
    summary = _summary(item)
    summary.update({
        "final_answer": item["final_answer"],
        "raw_output": None,
        "citations": item["citations"],
        "retriever": item["retriever"],
        "collection": item["collection"],
        "top_k": item["top_k"],
        "temperature": item["temperature"],
        "retrieved_chunks": chunks,
        "retrieved_context_ids": [c.get("chunk_id") for c in chunks],
        "context_recorded": bool(chunks),
        "eval_case_id": linked,
        "langfuse_url": trace_store.langfuse_url(trace_id),
        "feedback": feedback_rows,
        "cost_by_stage": {"retrieval_usd": 0.0, "generation_usd": cost, "tools_usd": 0.0},
        "spans": [
            {"name": "pre_retrieval_gate", "latency_ms": None, "tokens_in": 0, "tokens_out": 0,
             "cost_usd": 0.0, "logged": False},
            {"name": "retrieval", "latency_ms": item["retrieval_ms"], "tokens_in": 0, "tokens_out": 0,
             "cost_usd": 0.0, "logged": item["retrieval_ms"] is not None},
            {"name": "generation", "latency_ms": item["generation_ms"], "tokens_in": item["input_tokens"],
             "tokens_out": item["output_tokens"], "cost_usd": cost, "logged": item["generation_ms"] is not None},
            {"name": "citation_validation", "latency_ms": None, "tokens_in": 0, "tokens_out": 0,
             "cost_usd": 0.0, "logged": False},
        ],
    })
    return summary


class EvalCaseRequest(BaseModel):
    expected_behavior: str = Field(default="refusal", pattern="^(refusal|answer)$")
    mode: str = Field(default="corpus_gap", min_length=1, max_length=40)
    notes: str = Field(default="", max_length=500)


@router.post("/traces/{trace_id}/eval-case", status_code=201)
def create_eval_case(trace_id: str, body: EvalCaseRequest):
    from src.observability.eval_runner import add_case_from_trace

    try:
        item = trace_store.get_trace(trace_id)
    except TraceStoreError as exc:
        raise _store_error(exc)
    if item is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    notes = body.notes.strip() or "Created from a production trace in the Observability page"
    try:
        return add_case_from_trace(trace_id, item["question"], body.expected_behavior, body.mode, notes)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


# ------------------------------------------------------------------ cost / 10x

def _window(days):
    try:
        return trace_store.recent_window(days)
    except TraceStoreError as exc:
        raise _store_error(exc)


@router.get("/stats")
def stats(days: int = Query(default=90, ge=1, le=3650)):
    items, incomplete = _window(days)
    overall = group_stats(items)
    by_version = {}
    for item in items:
        by_version.setdefault(item["prompt_version"], []).append(item)
    versions = []
    for version, group in sorted(by_version.items()):
        entry = group_stats(group)
        entry["prompt_version"] = version
        versions.append(entry)

    per_minute = {}
    for item in items:
        key = (item["timestamp"] or "")[:16]
        bucket = per_minute.setdefault(key, [0, 0])
        bucket[0] += 1
        bucket[1] += (item["input_tokens"] or 0) + (item["output_tokens"] or 0)
    peak_rpm = max((b[0] for b in per_minute.values()), default=0)
    peak_tpm = max((b[1] for b in per_minute.values()), default=0)

    return {
        "window_days": days,
        "source": "langfuse",
        "scanned": len(items),
        "truncated": incomplete,
        "overall": overall,
        "stages": [
            {"stage": "retrieval", "avg_cost_usd": 0.0, "avg_latency_ms": overall["p50_retrieval_ms"],
             "note": "local ChromaDB, BM25 and embeddings, no API cost"},
            {"stage": "generation", "avg_cost_usd": overall["avg_cost_usd"], "avg_latency_ms": overall["p50_generation_ms"],
             "note": "LLM tokens, all of the API cost"},
            {"stage": "tools", "avg_cost_usd": 0.0, "avg_latency_ms": 0.0,
             "note": "this pipeline calls no tools"},
        ],
        "by_prompt_version": versions,
        "traffic": {"peak_requests_per_min": peak_rpm, "peak_tokens_per_min": peak_tpm},
    }


@router.get("/tenx")
def tenx(
    baseline_rpm: float | None = Query(default=None, gt=0, le=100000),
    multiplier: float | None = Query(default=None, ge=1, le=10000),
    days: int = Query(default=90, ge=1, le=3650),
):
    overall = group_stats(_window(days)[0])
    tokens_per_request = overall["avg_input_tokens"] + overall["avg_output_tokens"]
    baseline_rpm = _setting("capacity.tenx_baseline_rpm") if baseline_rpm is None else baseline_rpm
    multiplier = _setting("capacity.tenx_multiplier") if multiplier is None else multiplier
    rpm = baseline_rpm * multiplier
    needed_tpm = rpm * tokens_per_request
    limit_tpm = float(_setting("provider.tpm"))
    limit_rpd = float(_setting("provider.rpd"))
    limit_rpm = float(_setting("provider.rpm"))

    constraints = []
    if limit_tpm > 0:
        constraints.append({
            "name": "tokens per minute", "limit": limit_tpm, "needed": round(needed_tpm, 1),
            "ratio": round(needed_tpm / limit_tpm, 2),
            "minutes_to_break": 0.0 if needed_tpm > limit_tpm else None,
        })
    if limit_rpd > 0:
        constraints.append({
            "name": "requests per day", "limit": limit_rpd, "needed": round(rpm * 1440, 1),
            "ratio": round(rpm * 1440 / limit_rpd, 2),
            "minutes_to_break": round(limit_rpd / rpm, 1) if rpm * 1440 > limit_rpd else None,
        })
    if limit_rpm > 0:
        constraints.append({
            "name": "requests per minute", "limit": limit_rpm, "needed": round(rpm, 1),
            "ratio": round(rpm / limit_rpm, 2),
            "minutes_to_break": 0.0 if rpm > limit_rpm else None,
        })
    breaking = sorted([c for c in constraints if c["minutes_to_break"] is not None],
                      key=lambda c: c["minutes_to_break"])
    daily_cost = rpm * 1440 * overall["avg_cost_usd"]
    if breaking:
        first = breaking[0]
        verdict = (f"Rate limit breaks first: {first['name']} needs {first['needed']:g} against a limit of "
                   f"{first['limit']:g} ({first['ratio']}x over).")
    else:
        verdict = "No configured rate limit is exceeded at this volume."
    return {
        "baseline_rpm": baseline_rpm, "multiplier": multiplier, "requests_per_min": round(rpm, 2),
        "avg_tokens_per_request": round(tokens_per_request, 1),
        "avg_generation_ms": overall["avg_generation_ms"],
        "cost_per_request_usd": overall["avg_cost_usd"], "daily_cost_usd": round(daily_cost, 2),
        "constraints": constraints, "verdict": verdict,
        "assumptions": "Limits are the Provider limits settings (Admin, Settings). Baseline traffic is "
                       "an input, because no production traffic exists yet.",
    }


# ------------------------------------------------------------------ alerts

@router.get("/alerts/config")
def alerts_config():
    from src.observability.alerting import config_status
    return config_status()


@router.get("/alerts")
def list_alerts(status: Optional[str] = Query(default=None, pattern="^(sent|failed|suppressed|test)$"),
                limit: int = Query(default=50, ge=1, le=200)):
    clause, params = "", []
    if status:
        clause, params = " WHERE status = ?", [status]
    with get_db() as conn:
        rows = conn.execute(f"SELECT * FROM alerts{clause} ORDER BY id DESC LIMIT ?", params + [limit]).fetchall()
    return [dict(r) for r in rows]


_last_test = {"at": 0.0}


@router.post("/alerts/test")
def alerts_test():
    import time
    from src.observability.alerting import send_test_alert

    cooldown = _setting("alerts.test_cooldown_s")
    if time.time() - _last_test["at"] < cooldown:
        raise HTTPException(status_code=429, detail=f"Wait {cooldown} seconds between test emails")
    _last_test["at"] = time.time()
    ok, message = send_test_alert()
    if not ok and message.startswith("Missing settings"):
        raise HTTPException(status_code=400, detail=message)
    return {"ok": ok, "message": message}


# ------------------------------------------------------------------ drills

class DrillRequest(BaseModel):
    trace_id: str = Field(min_length=1, max_length=64)
    seconds: float = Field(ge=0, le=86400)
    slice: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=500)


@router.post("/drills", status_code=201)
def record_drill(body: DrillRequest, user: UserOut = Depends(require_admin)):
    if not trace_store.valid_trace_id(body.trace_id):
        raise HTTPException(status_code=404, detail="Trace not found")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO drills (created_at, trace_id, seconds, slice, notes, user_email) VALUES (?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), body.trace_id, body.seconds, body.slice, body.notes, user.email),
        )
    return {"seconds": body.seconds, "passed_bar": body.seconds < _setting("alerts.drill_bar_seconds")}


@router.get("/drills")
def list_drills(limit: int = Query(default=20, ge=1, le=100)):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM drills ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    bar = _setting("alerts.drill_bar_seconds")
    return [dict(r) | {"passed_bar": r["seconds"] < bar} for r in rows]


# ------------------------------------------------------------------ eval

@router.get("/eval/cases")
def eval_cases():
    from src.observability.eval_runner import load_cases

    last = {}
    with get_db() as conn:
        rows = conn.execute(
            "SELECT r.case_id, r.passed, r.run_id, s.prompt_version, s.started_at "
            "FROM eval_run_results r JOIN eval_suite_runs s ON s.run_id = r.run_id "
            "WHERE s.status != 'running' ORDER BY s.started_at DESC"
        ).fetchall()
    for row in rows:
        last.setdefault(row["case_id"], {
            "passed": bool(row["passed"]), "run_id": row["run_id"],
            "prompt_version": row["prompt_version"], "at": row["started_at"],
        })
    return [dict(case) | {"last_result": last.get(case["case_id"])} for case in load_cases()]


@router.post("/eval/cases/{case_id}/run")
def run_eval_case(case_id: str, user: UserOut = Depends(require_admin)):
    from src.observability.eval_runner import SuiteBusy, get_case, run_single

    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Unknown case")
    try:
        run_id, result = run_single(case, user.email)
    except SuiteBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"run_id": run_id, **result}


@router.post("/eval/runs", status_code=202)
def start_eval_suite(user: UserOut = Depends(require_admin)):
    from src.observability.eval_runner import SuiteBusy, start_suite

    try:
        return {"run_id": start_suite(user.email)}
    except SuiteBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/eval/runs")
def list_eval_runs(limit: int = Query(default=30, ge=1, le=100)):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM eval_suite_runs ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


@router.get("/eval/runs/{run_id}")
def get_eval_run(run_id: str):
    with get_db() as conn:
        run = conn.execute("SELECT * FROM eval_suite_runs WHERE run_id = ?", (run_id,)).fetchone()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        results = conn.execute(
            "SELECT case_id, passed, detail, answer, trace_id FROM eval_run_results WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
    return {
        "run": dict(run),
        "results": [dict(r) | {"passed": bool(r["passed"]), "detail": json.loads(r["detail"] or "[]")} for r in results],
    }


@router.get("/eval/diff")
def eval_diff(base: str = Query(min_length=1), head: str = Query(min_length=1)):
    def load(run_id):
        with get_db() as conn:
            if not conn.execute("SELECT 1 FROM eval_suite_runs WHERE run_id = ?", (run_id,)).fetchone():
                raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
            return {r["case_id"]: bool(r["passed"]) for r in conn.execute(
                "SELECT case_id, passed FROM eval_run_results WHERE run_id = ?", (run_id,))}

    before, after = load(base), load(head)
    rows = []
    for case_id in sorted(set(before) | set(after)):
        b, a = before.get(case_id), after.get(case_id)
        if b is None or a is None:
            change = "new" if b is None else "missing"
        elif b == a:
            change = "same_pass" if a else "same_fail"
        else:
            change = "fixed" if a else "regressed"
        rows.append({"case_id": case_id, "base": b, "head": a, "change": change})
    summary = {key: sum(1 for r in rows if r["change"] == key)
               for key in ("fixed", "regressed", "same_fail", "same_pass", "new", "missing")}
    return {"base": base, "head": head, "summary": summary, "rows": rows}


# ------------------------------------------------------------------ feedback inbox

@router.get("/feedback")
def list_feedback(
    rating: Optional[str] = Query(default=None, pattern="^(up|down)$"),
    status: Optional[str] = Query(default=None, pattern="^(new|reviewed)$"),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    where, params = [], []
    if rating:
        where.append("f.rating = ?")
        params.append(rating)
    if status:
        where.append("f.status = ?")
        params.append(status)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    with get_db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM feedback f{clause}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT f.* FROM feedback f{clause} ORDER BY f.updated_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        counts = {
            "new_down": conn.execute("SELECT COUNT(*) FROM feedback WHERE rating='down' AND status='new'").fetchone()[0],
            "down": conn.execute("SELECT COUNT(*) FROM feedback WHERE rating='down'").fetchone()[0],
            "up": conn.execute("SELECT COUNT(*) FROM feedback WHERE rating='up'").fetchone()[0],
        }
    items = []
    for row in rows:
        item = _feedback_row(row)
        item["langfuse_url"] = trace_store.langfuse_url(item["trace_id"])
        items.append(item)
    return {"total": total, "limit": limit, "offset": offset, "counts": counts, "items": items}


class ReviewRequest(BaseModel):
    status: str = Field(pattern="^(new|reviewed)$")
    admin_note: str = Field(default="", max_length=500)


@router.post("/feedback/{feedback_id}/review")
def review_feedback(feedback_id: int, body: ReviewRequest, user: UserOut = Depends(require_admin)):
    reviewed = body.status == "reviewed"
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE feedback SET status=?, admin_note=?, reviewed_by=?, reviewed_at=? WHERE id=?",
            (body.status, body.admin_note.strip() or None, user.email if reviewed else None,
             datetime.now(timezone.utc).isoformat() if reviewed else None, feedback_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Feedback not found")
    return {"id": feedback_id, "status": body.status}


# ------------------------------------------------------------------ demo

@router.post("/demo/plant", status_code=201)
def plant_demo_trace():
    if os.getenv("OBS_DEMO_TOOLS", "false").lower() != "true":
        raise HTTPException(status_code=404, detail="Demo tools are disabled")
    from src.generation.llm_client import default_model
    from src.observability.demo import plant_bad_trace

    record = plant_bad_trace(default_model())
    return {"trace_id": record["trace_id"], "timestamp": record["timestamp"]}

"""FastAPI router for the Week 10 multi-agent demo (admin only)."""

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import UserOut, require_admin

log = logging.getLogger("api.multiagent")
router = APIRouter(prefix="/api/multiagent", tags=["multiagent"])

_OUT_DIR = Path(__file__).resolve().parent.parent / "deliverables" / "week10"
_TEXT_FILES = {
    "race_table": "race_table.md",
    "handoffs_log": "handoffs.log",
    "failure_case": "failure_case.md",
    "verdict": "verdict.md",
    "a2a_lifecycle": "a2a_lifecycle.md",
}

_status: dict[str, Any] = {"status": "idle", "started_at": None, "error": None, "done": 0, "total": 10}
_status_lock = threading.Lock()


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    inject_failure: bool = False


def _read(name: str):
    path = _OUT_DIR / name
    return path.read_text("utf-8") if path.exists() else None


@router.get("/cases")
def get_cases(_user: UserOut = Depends(require_admin)):
    from evaluation.week10_race import load_cases

    return [
        {
            "case_id": c["case_id"],
            "question": c["question"],
            "mode": c["mode"],
            "expected_behavior": c["expected_behavior"],
        }
        for c in load_cases()
    ]


@router.get("/results")
def get_results(_user: UserOut = Depends(require_admin)):
    results_path = _OUT_DIR / "race_results.json"
    if not results_path.exists():
        raise HTTPException(404, "No multi-agent race results yet. Run the race first.")
    try:
        data = json.loads(results_path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.error("Failed to read multi-agent results: %s", exc)
        raise HTTPException(500, "Results file is corrupt")
    card = _read("agent_card.json")
    return {
        **data,
        "files": {key: _read(fname) for key, fname in _TEXT_FILES.items()},
        "agent_card": json.loads(card) if card else None,
    }


@router.get("/status")
def get_status(_user: UserOut = Depends(require_admin)):
    with _status_lock:
        return dict(_status)


@router.post("/run")
def run_race_endpoint(_user: UserOut = Depends(require_admin)):
    with _status_lock:
        if _status["status"] == "running":
            return {"status": "already_running"}
        _status.update(
            {"status": "running", "started_at": datetime.now().isoformat(), "error": None, "done": 0}
        )

    def _progress(done: int, total: int):
        with _status_lock:
            _status["done"] = done
            _status["total"] = total

    def _worker():
        try:
            from evaluation.week10_race import run_race

            run_race(pace=3.0, on_progress=_progress)
            with _status_lock:
                _status["status"] = "done"
        except Exception as exc:
            log.error("Multi-agent race failed: %s", exc)
            with _status_lock:
                _status["status"] = "error"
                _status["error"] = "Race run failed. Check server logs."

    threading.Thread(target=_worker, daemon=True).start()
    return {"status": "started"}


@router.post("/ask")
def ask_both(body: AskBody, _user: UserOut = Depends(require_admin)):
    """Run one question through the single agent and the orchestrator side by side."""
    from evaluation.assertions import run_assertions
    from evaluation.week10_multi_agent import COST_PER_1M_TOKENS, run_multi_agent
    from src.generation.answer import answer_question

    question = body.question.strip()
    try:
        t0 = time.perf_counter()
        single = answer_question(question)
        single_s = time.perf_counter() - t0
        t1 = time.perf_counter()
        multi = run_multi_agent(question, inject_failure=body.inject_failure)
        multi_s = time.perf_counter() - t1
    except Exception as exc:
        log.error("Multi-agent demo failed: %s", exc)
        raise HTTPException(502, "LLM call failed. Check server logs and rate limits.")

    def _assertions(answer: str, chunks: list):
        checks = run_assertions(answer, [c["chunk_id"] for c in chunks])
        return {c.name: c.passed for c in checks}

    single_tokens = single.input_tokens + single.output_tokens
    return {
        "question": question,
        "inject_failure": body.inject_failure,
        "single": {
            "answer": single.final_answer,
            "tokens": single_tokens,
            "cost_usd": single_tokens / 1_000_000 * COST_PER_1M_TOKENS,
            "latency_s": single_s,
            "chunk_ids": [c["chunk_id"] for c in single.retrieved_chunks],
            "assertions": _assertions(single.final_answer, single.retrieved_chunks),
        },
        "multi": {
            "answer": multi.final_answer,
            "tokens": multi.total_tokens,
            "cost_usd": multi.total_tokens / 1_000_000 * COST_PER_1M_TOKENS,
            "latency_s": multi_s,
            "chunk_ids": [c["chunk_id"] for c in multi.retrieved_chunks],
            "assertions": _assertions(multi.final_answer, multi.retrieved_chunks),
            "triage": multi.triage,
            "handoffs": multi.handoffs,
            "policy_lookup_failed": multi.policy_lookup_failed,
            "tool_attempts": multi.tool_attempts,
        },
    }

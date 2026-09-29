"""FastAPI router for the interactive Agent Chat feature.

Endpoints:
  GET  /api/agent/tickets         -- list ticket fixtures
  POST /api/agent/run             -- start an agent job (authenticated)
  GET  /api/agent/status/{job_id} -- poll status (authenticated)
"""

import json
import logging
import threading
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import UserOut, get_current_user
from api.database import get_db

log = logging.getLogger("api.agent")
router = APIRouter(prefix="/api/agent", tags=["agent"])


# ---------------------------------------------------------------------------
# SQLite-backed job store
# ---------------------------------------------------------------------------

def _create_job(job_id: str, user_email: str) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO jobs (job_id, user_email, status) VALUES (?,?,'running')",
            (job_id, user_email),
        )


def _append_step(job_id: str, step: dict) -> None:
    with get_db() as conn:
        row = conn.execute("SELECT steps FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row:
            steps = json.loads(row["steps"])
            steps.append(step)
            conn.execute("UPDATE jobs SET steps=? WHERE job_id=?", (json.dumps(steps), job_id))


def _finish_job(job_id: str, result: dict) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE jobs SET status='done', result=? WHERE job_id=?",
            (json.dumps(result), job_id),
        )


def _fail_job(job_id: str, error: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE jobs SET status='error', error=? WHERE job_id=?",
            (error, job_id),
        )


def _get_job(job_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    if not row:
        return None
    return {
        "status": row["status"],
        "steps": json.loads(row["steps"]),
        "result": json.loads(row["result"]) if row["result"] else None,
        "error": row["error"],
    }


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    ticket_id: str | None = None
    message: str | None = None
    tight_budget: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/tickets")
def list_tickets(_user: UserOut = Depends(get_current_user)):
    """Return the current ticket fixtures (reads from SQLite, falls back to hardcoded)."""
    try:
        with get_db() as conn:
            rows = conn.execute("SELECT * FROM tickets ORDER BY ticket_id").fetchall()
        if rows:
            from agent.tickets import EXPECTED, BRANCHING_IDS
            return [
                {
                    "ticket_id": r["ticket_id"],
                    "text": r["text"],
                    "customer_id": r["customer_id"],
                    "order_id": r["order_id"],
                    "expected": r["expected_verdict"],
                    "branching": r["ticket_id"] in BRANCHING_IDS,
                }
                for r in rows
            ]
    except Exception as exc:
        log.warning("SQLite unavailable for tickets, using hardcoded: %s", exc)

    from agent.tickets import TICKETS, EXPECTED, BRANCHING_IDS
    return [
        {
            "ticket_id": tid,
            "text": t["text"],
            "customer_id": t["customer_id"],
            "order_id": t["order_id"],
            "expected": EXPECTED[tid],
            "branching": tid in BRANCHING_IDS,
        }
        for tid, t in TICKETS.items()
    ]


@router.post("/run")
def run_agent_job(req: RunRequest, user: UserOut = Depends(get_current_user)):
    if not req.ticket_id and not req.message:
        raise HTTPException(400, "Provide ticket_id or message")

    job_id = str(uuid.uuid4())
    _create_job(job_id, user.email)

    def _worker():
        try:
            from agent.agent_loop import DEMO_MAX_ITERS, FREEFORM_SYSTEM_PROMPT, MAX_ITERS, run_agent
            from agent.tickets import EXPECTED
            from dataclasses import asdict

            def on_step(step: dict):
                _append_step(job_id, step)

            freeform = bool(req.message and not req.ticket_id)
            result = run_agent(
                ticket_id=req.ticket_id or "",
                expected_verdict=EXPECTED.get(req.ticket_id or "") if req.ticket_id else None,
                max_iters=DEMO_MAX_ITERS if req.tight_budget else MAX_ITERS,
                on_step=on_step,
                user_message=req.message if freeform else None,
                system_prompt_override=FREEFORM_SYSTEM_PROMPT if freeform else None,
            )
            if result.error or result.reply in ("[error]", "") or not result.reply.strip():
                _fail_job(job_id, result.error or "The agent did not produce a response. Please try again.")
            else:
                _finish_job(job_id, asdict(result))
        except Exception as exc:
            log.error("Agent job %s failed: %s", job_id, exc)
            _fail_job(job_id, "Agent run failed -- please try again")

    threading.Thread(target=_worker, daemon=True).start()
    return {"job_id": job_id}


@router.get("/status/{job_id}")
def get_job_status(job_id: str, _user: UserOut = Depends(get_current_user)):
    job = _get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job

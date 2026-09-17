"""FastAPI router for the interactive Agent Chat feature.

Endpoints:
  GET  /api/agent/tickets         -- list ticket fixtures
  POST /api/agent/run             -- start an agent job (authenticated)
  GET  /api/agent/status/{job_id} -- poll status (authenticated)
"""

import logging
import threading
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import UserOut, get_current_user

log = logging.getLogger("api.agent")
router = APIRouter(prefix="/api/agent", tags=["agent"])

# ---------------------------------------------------------------------------
# In-memory job store with TTL cleanup (60-minute retention)
# ---------------------------------------------------------------------------
_JOB_TTL_SECS = 3600
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _evict_old_jobs() -> None:
    cutoff = time.monotonic() - _JOB_TTL_SECS
    stale = [jid for jid, j in _jobs.items() if j.get("_created", 0) < cutoff]
    for jid in stale:
        del _jobs[jid]


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
        from api.database import get_db
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
    with _jobs_lock:
        _evict_old_jobs()
        _jobs[job_id] = {
            "status": "running",
            "steps": [],
            "result": None,
            "error": None,
            "_created": time.monotonic(),
            "_owner": user.email,
        }

    def _worker():
        try:
            from agent.agent_loop import DEMO_MAX_ITERS, FREEFORM_SYSTEM_PROMPT, MAX_ITERS, run_agent
            from agent.tickets import EXPECTED
            from dataclasses import asdict

            def on_step(step: dict):
                with _jobs_lock:
                    if job_id in _jobs:
                        _jobs[job_id]["steps"].append(step)

            freeform = bool(req.message and not req.ticket_id)
            result = run_agent(
                ticket_id=req.ticket_id or "",
                expected_verdict=EXPECTED.get(req.ticket_id or "") if req.ticket_id else None,
                max_iters=DEMO_MAX_ITERS if req.tight_budget else MAX_ITERS,
                on_step=on_step,
                user_message=req.message if freeform else None,
                system_prompt_override=FREEFORM_SYSTEM_PROMPT if freeform else None,
            )
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id]["status"] = "done"
                    _jobs[job_id]["result"] = asdict(result)
        except Exception as exc:
            log.error("Agent job %s failed: %s", job_id, exc)
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id]["status"] = "error"
                    _jobs[job_id]["error"] = "Agent run failed — please try again"

    threading.Thread(target=_worker, daemon=True).start()
    return {"job_id": job_id}


@router.get("/status/{job_id}")
def get_job_status(job_id: str, user: UserOut = Depends(get_current_user)):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found or expired")
    # Sanitise internal fields before returning
    return {k: v for k, v in job.items() if not k.startswith("_")}

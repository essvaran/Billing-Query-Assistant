"""FastAPI router for the Agent vs Workflow Race feature."""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from api.auth import UserOut, require_admin  # research tools: admin only (they spend model quota)

log = logging.getLogger("api.race")
router = APIRouter(prefix="/api/race", tags=["race"])

_RESULTS_PATH = Path(__file__).resolve().parent.parent / "agent" / "race_results.json"

_status: dict[str, Any] = {"status": "idle", "started_at": None, "error": None}
_status_lock = threading.Lock()


@router.get("/tickets")
def get_tickets(_user: UserOut = Depends(require_admin)):
    """The Week 7 ticket fixtures with expected verdicts (database, Admin, Tickets)."""
    from agent import tickets as fx
    return [
        {
            "ticket_id": tid,
            "text": t["text"],
            "customer_id": t["customer_id"],
            "order_id": t["order_id"],
            "expected": t.get("expected_verdict"),
            "branching": tid in fx.branching_ids(),
        }
        for tid, t in fx.tickets().items()
    ]


@router.get("/results")
def get_results(_user: UserOut = Depends(require_admin)):
    if not _RESULTS_PATH.exists():
        raise HTTPException(404, "No race results yet — run a race first")
    try:
        data = json.loads(_RESULTS_PATH.read_text("utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.error("Failed to read race results: %s", exc)
        raise HTTPException(500, "Race results file is corrupt")
    return JSONResponse(data)


@router.get("/status")
def get_status(_user: UserOut = Depends(require_admin)):
    with _status_lock:
        return dict(_status)


@router.post("/run")
def run_race(_user: UserOut = Depends(require_admin)):
    with _status_lock:
        if _status["status"] == "running":
            return {"status": "already_running"}
        _status.update({"status": "running", "started_at": datetime.now().isoformat(), "error": None})

    def _worker():
        try:
            from agent.race import race
            race()
            with _status_lock:
                _status["status"] = "done"
        except Exception as exc:
            log.error("Race failed: %s", exc)
            with _status_lock:
                _status["status"] = "error"
                _status["error"] = "Race run failed — check server logs"

    threading.Thread(target=_worker, daemon=True).start()
    return {"status": "started"}

"""FastAPI router for Trajectory Evaluation."""

import json
import logging
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.auth import UserOut, require_admin  # research tools: admin only (they spend model quota)

log = logging.getLogger("api.trajectory")
router = APIRouter(prefix="/api/trajectory", tags=["trajectory"])

_RESULTS_PATH = Path(__file__).resolve().parent.parent / "agent" / "trajectory_results.json"
_MITIGATION_RESULTS_PATH = Path(__file__).resolve().parent.parent / "agent" / "trajectory_mitigation.json"
_INJECTION_RESULTS_PATH = Path(__file__).resolve().parent.parent / "agent" / "injection_results.json"

_eval_status: dict[str, Any] = {"status": "idle", "started_at": None, "error": None, "progress": None}
_eval_lock = threading.Lock()

_mitigation_status: dict[str, Any] = {"status": "idle", "started_at": None, "error": None, "progress": None}
_mitigation_lock = threading.Lock()

_injection_status: dict[str, Any] = {"status": "idle", "started_at": None, "error": None}
_injection_lock = threading.Lock()


@router.get("/expected-sequences")
def get_expected_sequences(_user: UserOut = Depends(require_admin)):
    """Return expected tool sequences for display."""
    from agent import tickets as fx
    return [
        {
            "ticket_id": tid,
            "text": fx.tickets()[tid]["text"][:120],
            "expected_verdict": fx.expected()[tid],
            "branching": tid in fx.branching_ids(),
            "adversarial": tid in fx.adversarial_ids(),
            "sequences": fx.expected_sequences()[tid],
            "expected_args": fx.expected_args().get(tid, {}),
        }
        for tid in fx.tickets()
    ]


@router.post("/run")
def start_eval(_user: UserOut = Depends(require_admin)):
    """Start trajectory eval in a background thread."""
    with _eval_lock:
        if _eval_status["status"] == "running":
            return {"status": "already_running"}
        _eval_status.update({
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "error": None,
            "progress": None,
        })

    def _worker():
        try:
            from agent.trajectory_eval import run_full_eval

            def on_progress(event):
                with _eval_lock:
                    _eval_status["progress"] = event

            report = run_full_eval(on_progress=on_progress)
            report_dict = asdict(report)
            _RESULTS_PATH.write_text(json.dumps(report_dict, indent=2, default=str), encoding="utf-8")
            with _eval_lock:
                _eval_status["status"] = "done"
                _eval_status["progress"] = None
        except Exception as exc:
            log.error("Trajectory eval failed: %s", exc, exc_info=True)
            with _eval_lock:
                _eval_status["status"] = "error"
                _eval_status["error"] = str(exc)[:300]

    threading.Thread(target=_worker, daemon=True).start()
    return {"status": "started"}


@router.get("/status")
def get_eval_status(_user: UserOut = Depends(require_admin)):
    with _eval_lock:
        return dict(_eval_status)


@router.get("/results")
def get_eval_results(_user: UserOut = Depends(require_admin)):
    if not _RESULTS_PATH.exists():
        raise HTTPException(404, "No trajectory results yet -- run an eval first")
    try:
        data = json.loads(_RESULTS_PATH.read_text("utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.error("Failed to read trajectory results: %s", exc)
        raise HTTPException(500, "Trajectory results file is corrupt")
    return JSONResponse(data)


# --- Mitigation endpoints ---

@router.post("/mitigate")
def start_mitigation(_user: UserOut = Depends(require_admin)):
    """Run eval with argument validation mitigation, compare before/after."""
    with _mitigation_lock:
        if _mitigation_status["status"] == "running":
            return {"status": "already_running"}
        _mitigation_status.update({
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "error": None,
            "progress": None,
        })

    def _worker():
        try:
            from agent.mitigations import run_mitigation_comparison

            def on_progress(event):
                with _mitigation_lock:
                    _mitigation_status["progress"] = event

            report = run_mitigation_comparison(on_progress=on_progress)
            _MITIGATION_RESULTS_PATH.write_text(
                json.dumps(report, indent=2, default=str), encoding="utf-8"
            )
            with _mitigation_lock:
                _mitigation_status["status"] = "done"
                _mitigation_status["progress"] = None
        except Exception as exc:
            log.error("Mitigation eval failed: %s", exc, exc_info=True)
            with _mitigation_lock:
                _mitigation_status["status"] = "error"
                _mitigation_status["error"] = str(exc)[:300]

    threading.Thread(target=_worker, daemon=True).start()
    return {"status": "started"}


@router.get("/mitigation-status")
def get_mitigation_status(_user: UserOut = Depends(require_admin)):
    with _mitigation_lock:
        return dict(_mitigation_status)


@router.get("/mitigation-results")
def get_mitigation_results(_user: UserOut = Depends(require_admin)):
    if not _MITIGATION_RESULTS_PATH.exists():
        raise HTTPException(404, "No mitigation results yet -- run a mitigation first")
    try:
        data = json.loads(_MITIGATION_RESULTS_PATH.read_text("utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.error("Failed to read mitigation results: %s", exc)
        raise HTTPException(500, "Mitigation results file is corrupt")
    return JSONResponse(data)


# --- Injection test endpoints ---

@router.post("/injection/run")
def start_injection_test(_user: UserOut = Depends(require_admin)):
    """Run injection tests (undefended and defended)."""
    with _injection_lock:
        if _injection_status["status"] == "running":
            return {"status": "already_running"}
        _injection_status.update({
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "error": None,
        })

    def _worker():
        try:
            from agent.injection_test import run_all_injection_tests
            results = run_all_injection_tests()
            _INJECTION_RESULTS_PATH.write_text(
                json.dumps(results, indent=2, default=str), encoding="utf-8"
            )
            with _injection_lock:
                _injection_status["status"] = "done"
        except Exception as exc:
            log.error("Injection test failed: %s", exc, exc_info=True)
            with _injection_lock:
                _injection_status["status"] = "error"
                _injection_status["error"] = str(exc)[:300]

    threading.Thread(target=_worker, daemon=True).start()
    return {"status": "started"}


@router.get("/injection/status")
def get_injection_status(_user: UserOut = Depends(require_admin)):
    with _injection_lock:
        return dict(_injection_status)


@router.get("/injection/results")
def get_injection_results(_user: UserOut = Depends(require_admin)):
    if not _INJECTION_RESULTS_PATH.exists():
        raise HTTPException(404, "No injection results yet -- run an injection test first")
    try:
        data = json.loads(_INJECTION_RESULTS_PATH.read_text("utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.error("Failed to read injection results: %s", exc)
        raise HTTPException(500, "Injection results file is corrupt")
    return JSONResponse(data)

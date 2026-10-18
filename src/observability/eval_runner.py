"""Run eval cases from the UI/API and keep a history of runs.

Uses the same deterministic assertions as evaluation/run_eval.py. The LLM judge is not
used here, so a UI run is fast and its pass counts are reproducible.
"""
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from api.database import get_db

logger = logging.getLogger(__name__)

CASE_ID_PREFIX = "PF"
STALE_AFTER = timedelta(minutes=30)

_file_lock = threading.Lock()


class SuiteBusy(Exception):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- eval set (catalog suite 'docs')

def load_cases():
    from src.catalog import eval_store
    return eval_store.cases("docs")


def get_case(case_id):
    from src.catalog import eval_store
    case = eval_store.get_case(case_id)
    return case if case and case["suite"] == "docs" else None


def add_case_from_trace(trace_id, question, expected_behavior, mode, notes, actor="observability"):
    """Add a regression case linked to a production trace. Raises ValueError on duplicates."""
    from src.catalog import eval_store
    with _file_lock:
        for case in eval_store.cases("docs", include_inactive=True):
            if case.get("regression_trace_id") == trace_id:
                raise ValueError(f"trace already has eval case {case['case_id']}")
        case_id = eval_store.next_case_id(CASE_ID_PREFIX)
        data = {"question": question, "mode": mode, "expected_behavior": expected_behavior, "is_regression": True,
                "regression_trace_id": trace_id, "notes": notes}
        return eval_store.save_case(case_id, "docs", data, actor=actor, create=True, source="observability trace")


# ------------------------------------------------------------------ running

def evaluate_case(case):
    """Run one case through the live pipeline. Returns a result dict; never raises."""
    from evaluation.assertions import run_assertions
    from src.generation.answer import answer_question

    try:
        ans = answer_question(case["question"])
        checks = run_assertions(
            ans.final_answer,
            [c["chunk_id"] for c in ans.retrieved_chunks],
            case.get("expected_behavior"),
        )
        return {
            "case_id": case["case_id"],
            "passed": all(c.passed for c in checks),
            "detail": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks],
            "answer": ans.final_answer,
            "trace_id": ans.trace_id or None,
        }
    except Exception as exc:
        logger.exception("eval case %s crashed", case.get("case_id"))
        return {
            "case_id": case["case_id"],
            "passed": False,
            "detail": [{"name": "pipeline", "passed": False, "detail": f"{type(exc).__name__}: {exc}"[:300]}],
            "answer": None,
            "trace_id": None,
        }


def _insert_result(conn, run_id, result):
    conn.execute(
        "INSERT INTO eval_run_results (run_id, case_id, passed, detail, answer, trace_id) VALUES (?,?,?,?,?,?)",
        (run_id, result["case_id"], 1 if result["passed"] else 0,
         json.dumps(result["detail"]), result["answer"], result["trace_id"]),
    )


def _current_prompt_version():
    from src.generation.prompts import prompt_version
    return prompt_version()


def _claim_run(run_id, source, total, user_email):
    """Create a 'running' row, refusing if a fresh suite is already running."""
    cutoff = (datetime.now(timezone.utc) - STALE_AFTER).isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE eval_suite_runs SET status='error', finished_at=?, error='stale: process restarted' "
            "WHERE status='running' AND started_at < ?",
            (_now(), cutoff),
        )
        busy = conn.execute(
            "SELECT run_id FROM eval_suite_runs WHERE status='running' AND source LIKE 'ui%'"
        ).fetchone()
        if busy:
            raise SuiteBusy(f"run {busy['run_id']} is still running")
        conn.execute(
            "INSERT INTO eval_suite_runs (run_id, prompt_version, started_at, total, passed, status, source, user_email) "
            "VALUES (?,?,?,?,0,'running',?,?)",
            (run_id, _current_prompt_version(), _now(), total, source, user_email),
        )


def _finish_run(run_id, status, error=None):
    with get_db() as conn:
        conn.execute(
            "UPDATE eval_suite_runs SET status=?, finished_at=?, error=? WHERE run_id=?",
            (status, _now(), error, run_id),
        )


def run_single(case, user_email):
    run_id = f"case-{uuid4().hex[:10]}"
    _claim_run(run_id, "ui-case", 1, user_email)
    try:
        result = evaluate_case(case)
        with get_db() as conn:
            _insert_result(conn, run_id, result)
            conn.execute("UPDATE eval_suite_runs SET passed=? WHERE run_id=?", (1 if result["passed"] else 0, run_id))
        _finish_run(run_id, "done")
    except Exception as exc:
        _finish_run(run_id, "error", str(exc)[:300])
        raise
    return run_id, result


def _suite_worker(run_id, cases):
    passed = 0
    try:
        for case in cases:
            result = evaluate_case(case)
            passed += 1 if result["passed"] else 0
            with get_db() as conn:
                _insert_result(conn, run_id, result)
                conn.execute("UPDATE eval_suite_runs SET passed=? WHERE run_id=?", (passed, run_id))
        _finish_run(run_id, "done")
    except Exception as exc:
        logger.exception("eval suite %s failed", run_id)
        _finish_run(run_id, "error", str(exc)[:300])


def start_suite(user_email):
    """Start a full-suite run on a background thread. Returns the run id."""
    cases = load_cases()
    run_id = f"suite-{uuid4().hex[:10]}"
    _claim_run(run_id, "ui-suite", len(cases), user_email)
    threading.Thread(target=_suite_worker, args=(run_id, cases), daemon=True).start()
    return run_id

"""User feedback (thumbs up or down) on answers.

submit_feedback() stores the vote. A thumbs down also scores the Langfuse trace and emails the admin,
on a background thread so the user never waits for SMTP or Langfuse.
"""
import hashlib
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from api.database import get_db, insert_alert
from src.observability import alerting, email_template, trace_store
from src.observability.trace_store import TraceStoreError

logger = logging.getLogger(__name__)



def reasons() -> dict:
    """Thumbs-down reasons (catalog list docs_feedback_reason): code -> label, active only."""
    from src.catalog import ref
    return {v["code"]: v["label"] for v in ref.values("docs_feedback_reason")}


def _limit(key: str):
    from src.catalog import settings
    return settings.get(f"feedback.{key}")

_recent = {}
_recent_lock = threading.Lock()


class FeedbackError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _now():
    return datetime.now(timezone.utc).isoformat()


def _check_rate(user_email):
    now = time.time()
    with _recent_lock:
        stamps = [t for t in _recent.get(user_email, []) if now - t < _limit("window_s")]
        if len(stamps) >= _limit("submit_limit"):
            raise FeedbackError(429, "Too much feedback in a short time. Please wait a few minutes.")
        stamps.append(now)
        _recent[user_email] = stamps


def score_key(trace_id, user_email):
    return f"{trace_id}-{hashlib.sha1(user_email.lower().encode('utf-8')).hexdigest()[:10]}"


def submit_feedback(trace_id, user_email, rating, reason_code=None, comment=None):
    """Validate and store one vote. Returns {"id", "rating", "notify"}; notify is True for a new thumbs down."""
    if rating not in ("up", "down"):
        raise FeedbackError(422, "rating must be 'up' or 'down'")
    comment = (comment or "").strip()
    if len(comment) > _limit("max_comment"):
        raise FeedbackError(422, f"comment must be at most {_limit("max_comment")} characters")
    if rating == "down":
        if reason_code not in reasons():
            raise FeedbackError(422, "Please choose a reason for the thumbs down")
    else:
        reason_code, comment = None, ""
    if not trace_store.valid_trace_id(trace_id):
        raise FeedbackError(404, "Answer not found")
    _check_rate(user_email)
    try:
        item = trace_store.get_trace(trace_id)
    except TraceStoreError as exc:
        raise FeedbackError(503 if exc.status in (502, 503) else exc.status, exc.message)
    if item is None:
        raise FeedbackError(404, "Answer not found")
    snapshot = (item["question"], (item["final_answer"] or "")[:700], item.get("prompt_version"), item.get("timestamp"))

    now = _now()
    with get_db() as conn:
        previous = conn.execute(
            "SELECT id, rating FROM feedback WHERE trace_id = ? AND user_email = ?", (trace_id, user_email)
        ).fetchone()
        notify = rating == "down" and (previous is None or previous["rating"] != "down")
        if previous is None:
            cursor = conn.execute(
                "INSERT INTO feedback (trace_id, user_email, rating, reason_code, comment, status, created_at, updated_at, "
                "question, answer_preview, prompt_version, answered_at) VALUES (?,?,?,?,?,'new',?,?,?,?,?,?)",
                (trace_id, user_email, rating, reason_code, comment or None, now, now, *snapshot),
            )
            feedback_id = cursor.lastrowid
        else:
            feedback_id = previous["id"]
            conn.execute(
                "UPDATE feedback SET rating=?, reason_code=?, comment=?, updated_at=?, "
                "question=?, answer_preview=?, prompt_version=?, answered_at=?, "
                "status=CASE WHEN ? THEN 'new' ELSE status END WHERE id=?",
                (rating, reason_code, comment or None, now, *snapshot, 1 if notify else 0, feedback_id),
            )
    return {"id": feedback_id, "rating": rating, "notify": notify, "trace": item}


# ------------------------------------------------------------------ side effects

def _history(status, trace_id, reason, detail=None):
    try:
        insert_alert("negative_feedback", status, trace_id, reason, detail)
    except Exception:
        logger.exception("could not record feedback email history")


def _sent_in_last_hour():
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with get_db() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE alert_type='negative_feedback' AND status='sent' AND ts > ?", (cutoff,)
        ).fetchone()[0]


def email_admin(user_email, trace_id, reason_code, comment, record=None):
    """Email the admin about a thumbs down. Records the outcome in alert history. Never raises."""
    reason = reasons().get(reason_code, reason_code or "no reason given")
    try:
        if not alerting.is_enabled():
            _history("suppressed", trace_id, reason, "email alerts are disabled")
            return False
        missing = alerting.missing_settings()
        if missing:
            _history("failed", trace_id, reason, "missing settings: " + ", ".join(missing))
            return False
        cap = _limit("email_max_per_hour")
        if _sent_in_last_hour() >= cap:
            _history("suppressed", trace_id, reason, f"hourly cap of {cap} feedback emails reached")
            return False
        record = record or {"trace_id": trace_id}
        subject, text, html = email_template.render_feedback(user_email, reason, comment, record)
        alerting.send_alert_email(subject, text, html)
        _history("sent", trace_id, reason, user_email)
        return True
    except Exception as exc:
        _history("failed", trace_id, reason, f"{type(exc).__name__}: {exc}"[:300])
        logger.exception("feedback email failed for %s", trace_id)
        return False


def score_in_langfuse(user_email, trace_id, rating, reason_code, comment):
    from src.generation.langfuse_client import score_feedback

    return score_feedback(trace_id, score_key(trace_id, user_email), rating, reason_code, comment)


def run_side_effects(user_email, trace_id, rating, reason_code, comment, notify, record=None):
    score_in_langfuse(user_email, trace_id, rating, reason_code, (comment or "").strip() or None)
    if notify:
        email_admin(user_email, trace_id, reason_code, comment, record)


def submit_and_notify(trace_id, user_email, rating, reason_code=None, comment=None):
    """Store the vote, then score Langfuse and email the admin without blocking the caller."""
    result = submit_feedback(trace_id, user_email, rating, reason_code, comment)
    threading.Thread(
        target=run_side_effects,
        args=(user_email, trace_id, result["rating"], reason_code, comment, result["notify"], result["trace"]),
        daemon=True,
    ).start()
    return result

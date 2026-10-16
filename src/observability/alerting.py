"""Email alerts for critical traces. The SMTP send runs on a background daemon thread."""
import logging
import os
import smtplib
import threading
import time
from email.message import EmailMessage

from src.observability.email_template import render_alert, render_test

logger = logging.getLogger(__name__)

RATE_LIMIT_SECONDS = 300
_last_sent = {}
_lock = threading.Lock()

REFUSAL_PREFIXES = (
    "I don't have enough information to answer that",
    "I cannot answer that from the indexed help-centre articles",
)
BLOCKLIST_KEYWORDS = ("refund", "compensation", "guarantee")
REQUIRED_SETTINGS = ("ALERT_EMAIL_FROM", "ALERT_EMAIL_TO", "ALERT_EMAIL_PASSWORD")


def is_enabled():
    return os.getenv("ALERT_EMAIL_ENABLED", "false").lower() == "true"


def missing_settings():
    return [name for name in REQUIRED_SETTINGS if not os.getenv(name, "").strip()]


def _mask_email(value):
    if not value or "@" not in value:
        return value or ""
    local, domain = value.split("@", 1)
    return (local[:2] + "***@" + domain) if len(local) > 2 else ("***@" + domain)


def config_status():
    """Non-secret view of the alert configuration, safe to return to an admin UI."""
    return {
        "enabled": is_enabled(),
        "smtp_host": os.getenv("ALERT_SMTP_HOST", "smtp.gmail.com"),
        "smtp_port": int(os.getenv("ALERT_SMTP_PORT", "587")),
        "email_from": _mask_email(os.getenv("ALERT_EMAIL_FROM", "")),
        "email_to": _mask_email(os.getenv("ALERT_EMAIL_TO", "")),
        "password_set": bool(os.getenv("ALERT_EMAIL_PASSWORD", "").strip()),
        "missing": missing_settings(),
        "cost_threshold_usd": float(os.getenv("ALERT_COST_THRESHOLD", "0.001")),
        "latency_threshold_ms": float(os.getenv("ALERT_LATENCY_THRESHOLD_MS", "10000")),
        "rate_limit_seconds": RATE_LIMIT_SECONDS,
        "conditions": [
            "ungrounded_answer: non-refusal answer without valid citations",
            "cost_outlier: cost above the cost threshold",
            "slow_request: latency above the latency threshold",
            "pipeline_error: any error recorded on the trace",
            "blocklist_keyword: answer mentions refund, compensation or guarantee",
            "negative_feedback: a user gives an answer a thumbs down (one email per vote, up to the hourly cap)",
        ],
    }


def _is_refusal(answer):
    return answer.strip().startswith(REFUSAL_PREFIXES)


def evaluate_conditions(record):
    """Return [(alert_type, reason)] for every critical condition the trace trips."""
    alerts = []
    answer = record.get("final_answer") or ""
    refusal = _is_refusal(answer)
    cost_threshold = float(os.getenv("ALERT_COST_THRESHOLD", "0.001"))
    latency_threshold = float(os.getenv("ALERT_LATENCY_THRESHOLD_MS", "10000"))

    if not refusal and not record.get("citations_valid"):
        alerts.append(("ungrounded_answer", "non-refusal answer without valid citations"))
    if (record.get("cost_usd") or 0.0) > cost_threshold:
        alerts.append(("cost_outlier", f"cost_usd {record['cost_usd']} above {cost_threshold}"))
    if (record.get("total_ms") or 0.0) > latency_threshold:
        alerts.append(("slow_request", f"total_ms {record['total_ms']} above {latency_threshold}"))
    if record.get("error"):
        alerts.append(("pipeline_error", str(record["error"])[:200]))
    if not refusal and any(k in answer.lower() for k in BLOCKLIST_KEYWORDS):
        alerts.append(("blocklist_keyword", "answer makes refund/compensation/guarantee claims"))
    return alerts


def send_alert_email(subject, body, html=None):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ["ALERT_EMAIL_FROM"]
    msg["To"] = os.environ["ALERT_EMAIL_TO"]
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    host = os.getenv("ALERT_SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("ALERT_SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        smtp.starttls()
        smtp.login(os.environ["ALERT_EMAIL_FROM"], os.environ["ALERT_EMAIL_PASSWORD"])
        smtp.send_message(msg)


def _record(alert_type, status, trace_id=None, reason=None, detail=None):
    try:
        from api.database import insert_alert
        insert_alert(alert_type, status, trace_id, reason, detail)
    except Exception:
        logger.exception("could not record alert history")


def _send_alerts(alerts, record):
    for alert_type, reason in alerts:
        now = time.time()
        with _lock:
            if now - _last_sent.get(alert_type, 0.0) < RATE_LIMIT_SECONDS:
                _record(alert_type, "suppressed", record.get("trace_id"), reason, "rate limited")
                continue
            _last_sent[alert_type] = now
        try:
            subject, body, html = render_alert(alert_type, reason, record, RATE_LIMIT_SECONDS // 60)
            send_alert_email(subject, body, html)
            _record(alert_type, "sent", record.get("trace_id"), reason)
            logger.info("alert sent: %s", subject)
        except Exception as exc:
            _record(alert_type, "failed", record.get("trace_id"), reason, f"{type(exc).__name__}: {exc}"[:300])
            logger.exception("alert email failed: %s %s", alert_type, record.get("trace_id"))


def check_and_alert(record):
    """Evaluate conditions inline (no I/O), then send email on a daemon thread."""
    if not is_enabled():
        return
    alerts = evaluate_conditions(record)
    if alerts:
        threading.Thread(target=_send_alerts, args=(alerts, record), daemon=True).start()


def send_test_alert():
    """Send one test email synchronously. Returns (ok, message). Never raises."""
    missing = missing_settings()
    if missing:
        return False, "Missing settings: " + ", ".join(missing)
    try:
        subject, body, html = render_test(os.getenv("ALERT_SMTP_HOST", "smtp.gmail.com"))
        send_alert_email(subject, body, html)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"[:300]
        _record("test", "failed", None, "manual test", message)
        return False, message
    _record("test", "test", None, "manual test", "delivered to SMTP server")
    return True, "Test email handed to the SMTP server."

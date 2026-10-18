"""HTML and plain-text bodies for alert emails.

Email clients ignore most CSS, so the layout uses tables and inline styles only.
Every dynamic value is HTML-escaped: answers and questions are untrusted text.
"""
import os
from datetime import datetime, timezone
from html import escape
from urllib.parse import quote

def alert_info(alert_type: str) -> dict:
    """Title, colour and the two explanatory lines for an alert email (catalog list alert_type)."""
    from src.catalog import ref
    v = ref.get("alert_type", alert_type) or ref.get("alert_type", "default") or {"label": "Alert", "meta": {}}
    m = v["meta"]
    return {"title": v["label"], "color": m.get("color", "#495057"), "what": m.get("what", ""), "action": m.get("action", "")}


def app_url():
    url = os.getenv("ALERT_APP_URL", "http://localhost:4200").strip().rstrip("/")
    return url if url.startswith(("http://", "https://")) else "http://localhost:4200"


def trace_link(trace_id):
    if not trace_id or trace_id == "test-trace":
        return app_url() + "/admin?tab=observability"
    return f"{app_url()}/admin?tab=observability&trace={quote(str(trace_id), safe='')}"


def _fmt_time(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        return str(value or "unknown")


def _usd(value):
    return "n/a" if value is None else (f"${value:.6f}" if value < 0.01 else f"${value:.4f}")


def _row(label, value):
    return (
        '<tr>'
        f'<td style="padding:6px 0;color:#868e96;font-size:13px;width:140px;vertical-align:top">{escape(label)}</td>'
        f'<td style="padding:6px 0;color:#212529;font-size:13px;vertical-align:top">{value}</td>'
        '</tr>'
    )


def _block(label, text):
    return (
        f'<div style="margin-top:18px;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#868e96;font-weight:bold">{escape(label)}</div>'
        '<div style="margin-top:6px;padding:12px 14px;background:#f8f9fa;border-left:3px solid #ced4da;'
        'border-radius:4px;font-size:14px;line-height:1.5;color:#212529;white-space:pre-wrap">'
        f'{escape(text)}</div>'
    )


def _shell(color, badge, heading, body_html, footer):
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        '<body style="margin:0;padding:0;background:#f1f3f5;font-family:Segoe UI,Helvetica,Arial,sans-serif">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f3f5;padding:24px 12px"><tr><td align="center">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;'
        'border-radius:10px;overflow:hidden;border:1px solid #dee2e6">'
        f'<tr><td style="background:{color};padding:18px 24px;color:#ffffff">'
        f'<div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.85">{escape(badge)}</div>'
        f'<div style="font-size:20px;font-weight:bold;margin-top:4px">{escape(heading)}</div></td></tr>'
        f'<tr><td style="padding:22px 24px">{body_html}</td></tr>'
        f'<tr><td style="padding:14px 24px;background:#f8f9fa;border-top:1px solid #e9ecef;font-size:12px;color:#868e96;line-height:1.5">{footer}</td></tr>'
        '</table></td></tr></table></body></html>'
    )


def _button(url, label, color):
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:22px"><tr>'
        f'<td style="background:{color};border-radius:6px">'
        f'<a href="{escape(url, quote=True)}" style="display:inline-block;padding:11px 20px;color:#ffffff;'
        f'font-size:14px;font-weight:bold;text-decoration:none">{escape(label)}</a></td></tr></table>'
    )


def render_alert(alert_type, reason, record, rate_limit_minutes=5):
    """Return (subject, plain_text, html) for one alert."""
    info = alert_info(alert_type)
    trace_id = record.get("trace_id")
    link = trace_link(trace_id)
    answer = (record.get("final_answer") or "")
    shown_answer = answer[:700] + (" ..." if len(answer) > 700 else "")
    when = _fmt_time(record.get("timestamp"))
    latency = record.get("total_ms")

    subject = f"[RAG Alert] {info['title']} - trace {str(trace_id)[:8]}"

    text = "\n".join([
        info["title"].upper(),
        "",
        info["what"],
        f"Why it fired: {reason}",
        f"What to do: {info['action']}",
        "",
        f"Time:           {when}",
        f"Trace id:       {trace_id}",
        f"Prompt version: {record.get('prompt_version')}",
        f"Model:          {record.get('model')}",
        f"Cost:           {_usd(record.get('cost_usd'))}",
        f"Latency:        {'n/a' if latency is None else str(round(latency)) + ' ms'}",
        "",
        "Question:",
        str(record.get("question") or ""),
        "",
        "Answer:",
        shown_answer,
        "",
        f"Open the trace: {link}",
    ])

    details = "".join([
        _row("Time", escape(when)),
        _row("Trace id", f'<span style="font-family:Consolas,monospace;font-size:12px">{escape(str(trace_id))}</span>'),
        _row("Prompt version", escape(str(record.get("prompt_version")))),
        _row("Model", escape(str(record.get("model")))),
        _row("Cost", escape(_usd(record.get("cost_usd")))),
        _row("Latency", "n/a" if latency is None else escape(f"{round(latency)} ms")),
    ])
    body = (
        f'<div style="font-size:15px;line-height:1.55;color:#212529">{escape(info["what"])}</div>'
        '<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin-top:14px;'
        'background:#fff9db;border:1px solid #ffec99;border-radius:6px"><tr><td style="padding:10px 14px;font-size:13px;'
        'line-height:1.5;color:#664d03">'
        f'<strong>Why it fired:</strong> {escape(str(reason))}<br><strong>What to do:</strong> {escape(info["action"])}</td></tr></table>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin-top:18px">{details}</table>'
        + _block("Question", str(record.get("question") or ""))
        + _block("Answer", shown_answer)
        + _button(link, "Open this trace", info["color"])
    )
    footer = (
        f"You receive at most one email per alert type every {rate_limit_minutes} minutes, so more traces may have "
        "matched. The Observability page lists every alert, including suppressed ones."
    )
    return subject, text, _shell(info["color"], "RAG support assistant", info["title"], body, footer)


def render_test(smtp_host):
    """Return (subject, plain_text, html) for the test email."""
    info = alert_info("test")
    link = trace_link(None)
    text = "\n".join([
        "TEST ALERT",
        "",
        "Alert delivery works. This message was sent from the Observability page.",
        f"SMTP server: {smtp_host}",
        "",
        f"Open the page: {link}",
    ])
    body = (
        '<div style="font-size:15px;line-height:1.55;color:#212529">Alert delivery works. '
        'This message was sent from the Observability page.</div>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin-top:14px">{_row("SMTP server", escape(smtp_host))}'
        f'{_row("Sent at", escape(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")))}</table>'
        + _button(link, "Open Observability", info["color"])
    )
    footer = "Real alerts look like this, with the question, the answer, cost and a link to the trace."
    return "[RAG Alert] Test alert", text, _shell(info["color"], "RAG support assistant", info["title"], body, footer)


def render_feedback(user_email, reason, comment, record):
    """Return (subject, plain_text, html) for a thumbs-down email to the admin."""
    from src.generation.langfuse_client import trace_url

    trace_id = record.get("trace_id")
    review_link = trace_link(trace_id)
    langfuse_link = trace_url(trace_id)
    answer = record.get("final_answer") or ""
    shown_answer = answer[:700] + (" ..." if len(answer) > 700 else "")
    question = str(record.get("question") or "")
    comment = (comment or "").strip()
    color = "#c92a2a"

    subject = f"[RAG Feedback] Thumbs down: {reason} - {question[:60]}"
    text_lines = [
        "A USER GAVE AN ANSWER A THUMBS DOWN",
        "",
        f"User:    {user_email}",
        f"Reason:  {reason}",
    ]
    if comment:
        text_lines.append(f"Comment: {comment}")
    text_lines += [
        "",
        "Question:", question, "",
        "Answer they disagreed with:", shown_answer, "",
        f"Prompt version: {record.get('prompt_version')}",
        f"Trace id:       {trace_id}",
        "",
        f"Review the trace: {review_link}",
    ]
    if langfuse_link:
        text_lines.append(f"Open in Langfuse: {langfuse_link}")
    text = "\n".join(text_lines)

    details = "".join([
        _row("User", escape(str(user_email))),
        _row("Reason", f'<strong style="color:{color}">{escape(reason)}</strong>'),
        _row("Time", escape(_fmt_time(record.get("timestamp")))),
        _row("Prompt version", escape(str(record.get("prompt_version")))),
        _row("Model", escape(str(record.get("model")))),
        _row("Trace id", f'<span style="font-family:Consolas,monospace;font-size:12px">{escape(str(trace_id))}</span>'),
    ])
    buttons = _button(review_link, "Review the trace", color)
    if langfuse_link:
        buttons += (
            '<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:10px"><tr>'
            '<td style="border:1px solid #adb5bd;border-radius:6px">'
            f'<a href="{escape(langfuse_link, quote=True)}" style="display:inline-block;padding:10px 18px;color:#343a40;'
            'font-size:14px;font-weight:bold;text-decoration:none">Open in Langfuse</a></td></tr></table>'
        )
    body = (
        '<div style="font-size:15px;line-height:1.55;color:#212529">A user disagreed with an answer. '
        'Check the retrieved context and the prompt, then turn it into an eval case.</div>'
        f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin-top:14px">{details}</table>'
        + (_block("Why they disagree", comment) if comment else "")
        + _block("Question", question)
        + _block("Answer they disagreed with", shown_answer)
        + buttons
    )
    footer = (
        "Sent because a user pressed thumbs down. The Feedback tab in Admin, Observability lists every vote, "
        "and you can mark each one reviewed."
    )
    return subject, text, _shell(color, "User feedback", "Thumbs down on an answer", body, footer)

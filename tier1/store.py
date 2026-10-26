"""Reads and writes behind the Tier-1 API: queue, results, human decisions, feedback, escalations,
jobs and the numbers on the insights page. Pure SQLite; no business logic (that lives in service.py)."""
import difflib
import json
import statistics
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from src.config import PROJECT_ROOT
from tier1 import db
from tier1.masking import mask_email, mask_name

EVAL_DIR = PROJECT_ROOT / "docs" / "archive" / "deliverables" / "week12" / "eval"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- AI results -------------------------------------------------------------------------------

def save_result(ticket_id: str, resp: dict) -> None:
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO ai_results (ticket_id, trace_id, created_at, decision, reason, cost_usd, latency_ms, "
            "total_tokens, response_json) VALUES (?,?,?,?,?,?,?,?,?)",
            (ticket_id, resp["trace_id"], _now(), resp["decision"], resp.get("reason"), resp.get("cost_usd"),
             resp.get("latency_ms"), resp.get("total_tokens"), json.dumps(resp)))


def latest_result(ticket_id: str) -> dict | None:
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM ai_results WHERE ticket_id=? ORDER BY id DESC LIMIT 1", (ticket_id,)).fetchone()
    if not row:
        return None
    return {**json.loads(row["response_json"]), "created_at": row["created_at"]}


def result_by_trace(trace_id: str) -> dict | None:
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM ai_results WHERE trace_id=?", (trace_id,)).fetchone()
    return {**json.loads(row["response_json"]), "ticket_id": row["ticket_id"]} if row else None


# --- queue --------------------------------------------------------------------------------------

def _order_age(purchase_date: str) -> int:
    return (db.as_of() - date.fromisoformat(purchase_date)).days


def ticket_status(ai: dict | None, decision: dict | None) -> str:
    if decision:
        return {"approve": "approved", "edit": "approved", "escalate": "escalated", "reject": "rejected"}[decision["action"]]
    if ai is None:
        return "new"
    return "escalated_by_ai" if ai["decision"] == "ESCALATE" else "draft_ready"


def list_tickets(status: str = "", q: str = "", policy: str = "", region: str = "", page: int = 1,
                 page_size: int = 25) -> dict:
    """Queue rows. Never includes the eval ground truth (kind, expected_*, gold_slug)."""
    sql = ("SELECT t.ticket_id, t.subject, t.body, t.customer_id, t.order_id, c.name, c.email, c.region, c.plan, "
           "c.policy_version, o.purchase_date FROM tickets t JOIN customers c USING(customer_id) "
           "JOIN orders o ON o.order_id = t.order_id WHERE 1=1")
    args: list = []
    if q:
        sql += " AND (t.subject LIKE ? OR t.body LIKE ? OR t.ticket_id LIKE ?)"
        args += [f"%{q}%"] * 3
    if policy:
        sql += " AND c.policy_version = ?"
        args.append(policy)
    if region:
        sql += " AND c.region = ?"
        args.append(region)
    sql += " ORDER BY t.ticket_id"
    with db.get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql, args)]
        last_ai = {r["ticket_id"]: dict(r) for r in conn.execute(
            "SELECT a.ticket_id, a.decision, a.reason FROM ai_results a JOIN "
            "(SELECT ticket_id, MAX(id) mid FROM ai_results GROUP BY ticket_id) m ON a.id = m.mid")}
        last_dec = {r["ticket_id"]: dict(r) for r in conn.execute(
            "SELECT d.ticket_id, d.action FROM decisions d JOIN "
            "(SELECT ticket_id, MAX(id) mid FROM decisions GROUP BY ticket_id) m ON d.id = m.mid")}
    items = []
    for r in rows:
        st = ticket_status(last_ai.get(r["ticket_id"]), last_dec.get(r["ticket_id"]))
        if status and st != status:
            continue
        items.append({
            "ticket_id": r["ticket_id"], "subject": r["subject"] or "", "preview": (r["body"] or "")[:140],
            "customer": mask_name(r["name"]), "customer_email": mask_email(r["email"]), "region": r["region"],
            "plan": r["plan"], "policy_version": r["policy_version"], "order_age_days": _order_age(r["purchase_date"]),
            "status": st, "ai_reason": (last_ai.get(r["ticket_id"]) or {}).get("reason") or None,
        })
    total = len(items)
    start = (max(page, 1) - 1) * page_size
    return {"total": total, "page": page, "page_size": page_size, "items": items[start:start + page_size],
            "counts": _count_by_status(rows, last_ai, last_dec)}


def _count_by_status(rows, last_ai, last_dec) -> dict:
    counts: dict[str, int] = {}
    for r in rows:
        st = ticket_status(last_ai.get(r["ticket_id"]), last_dec.get(r["ticket_id"]))
        counts[st] = counts.get(st, 0) + 1
    return counts


def ticket_detail(ticket_id: str) -> dict | None:
    t = db.get_ticket(ticket_id)
    if t is None:
        return None
    cust, order = db.get_customer(t["customer_id"]), db.get_order(t["order_id"])
    with db.get_conn() as conn:
        decisions = [dict(r) for r in conn.execute(
            "SELECT action, created_at, user_email, edit_ratio FROM decisions WHERE ticket_id=? ORDER BY id DESC", (ticket_id,))]
    return {
        "ticket_id": ticket_id, "subject": t["subject"] or "", "body": t["body"],
        "customer": {"customer_id": cust["customer_id"], "name": cust["name"], "email": cust["email"],
                     "region": cust["region"], "plan": cust["plan"]},
        "order": {**order, "age_days": _order_age(order["purchase_date"])},
        "ai": latest_result(ticket_id), "decisions": decisions,
    }


# --- human decisions and feedback ---------------------------------------------------------------

def record_decision(ticket_id: str, action: str, text: str | None, user_email: str) -> dict:
    ai = latest_result(ticket_id)
    ratio = None
    drafted = (ai or {}).get("customer_reply") or (ai or {}).get("reply")
    if action in ("approve", "edit") and drafted and text is not None:
        ratio = round(1 - difflib.SequenceMatcher(None, drafted, text).ratio(), 3)  # 0 means sent as drafted
        action = "approve" if ratio == 0 else "edit"
    with db.get_conn() as conn:
        conn.execute("INSERT INTO decisions (ticket_id, trace_id, created_at, action, final_text, edit_ratio, user_email) "
                     "VALUES (?,?,?,?,?,?,?)",
                     (ticket_id, ai["trace_id"] if ai else None, _now(), action, text, ratio, user_email))
    return {"action": action, "edit_ratio": ratio}


def add_feedback(ticket_id: str | None, trace_id: str, reason: str, comment: str | None, user_email: str) -> int:
    with db.get_conn() as conn:
        cur = conn.execute("INSERT INTO ticket_feedback (ticket_id, trace_id, created_at, reason, comment, user_email) "
                           "VALUES (?,?,?,?,?,?)", (ticket_id, trace_id, _now(), reason, comment, user_email))
        return cur.lastrowid


def list_feedback(status: str = "") -> list[dict]:
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM ticket_feedback" + (" WHERE status=?" if status else "") +
                            " ORDER BY id DESC LIMIT 200", (status,) if status else ()).fetchall()
    return [dict(r) for r in rows]


def get_feedback(feedback_id: int) -> dict | None:
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM ticket_feedback WHERE id=?", (feedback_id,)).fetchone()
    return dict(row) if row else None


def link_feedback_case(feedback_id: int, case_id: str) -> None:
    with db.get_conn() as conn:
        conn.execute("UPDATE ticket_feedback SET status='case_created', eval_case_id=? WHERE id=?", (case_id, feedback_id))


# --- escalations ---------------------------------------------------------------------------------

def list_escalations(status: str = "") -> list[dict]:
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM handoffs" + (" WHERE status=?" if status else "") +
                            " ORDER BY created_at DESC LIMIT 200", (status,) if status else ()).fetchall()
    return [dict(r) for r in rows]


def update_escalation(handoff_id: str, status: str, user_email: str) -> bool:
    with db.get_conn() as conn:
        cur = conn.execute("UPDATE handoffs SET status=?, claimed_by=?, claimed_at=? WHERE handoff_id=?",
                           (status, user_email, _now(), handoff_id))
        return cur.rowcount > 0


# --- jobs ----------------------------------------------------------------------------------------

def create_job(user_email: str, trace_id: str) -> str:
    job_id = uuid.uuid4().hex
    with db.get_conn() as conn:
        conn.execute("INSERT INTO jobs (job_id, created_at, user_email, status, trace_id) VALUES (?,?,?,?,?)",
                     (job_id, _now(), user_email, "running", trace_id))
    return job_id


def append_step(job_id: str, step: dict) -> None:
    with db.get_conn() as conn:
        row = conn.execute("SELECT steps FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row:
            steps = json.loads(row["steps"]) + [step]
            conn.execute("UPDATE jobs SET steps=? WHERE job_id=?", (json.dumps(steps), job_id))


def finish_job(job_id: str, result: dict) -> None:
    with db.get_conn() as conn:
        conn.execute("UPDATE jobs SET status='done', result=? WHERE job_id=?", (json.dumps(result), job_id))


def fail_job(job_id: str, error: str) -> None:
    with db.get_conn() as conn:
        conn.execute("UPDATE jobs SET status='error', error=? WHERE job_id=?", (error, job_id))


def owns_trace(trace_id: str, user_email: str) -> bool:
    """True when this user started the job that produced the trace (the only answers they may report)."""
    with db.get_conn() as conn:
        row = conn.execute("SELECT 1 FROM jobs WHERE trace_id=? AND lower(user_email)=lower(?)",
                           (trace_id, user_email)).fetchone()
    return row is not None


def fail_interrupted_jobs() -> int:
    """At startup: a job still 'running' lost its worker thread when the process stopped, so end it
    instead of letting the UI poll forever."""
    with db.get_conn() as conn:
        cur = conn.execute("UPDATE jobs SET status='error', error=? WHERE status='running'",
                           ("Interrupted by a restart. Run the ticket again.",))
    return cur.rowcount


def get_job(job_id: str) -> dict | None:
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    if not row:
        return None
    return {"job_id": row["job_id"], "status": row["status"], "trace_id": row["trace_id"],
            "steps": json.loads(row["steps"]), "result": json.loads(row["result"]) if row["result"] else None,
            "error": row["error"], "owner": row["user_email"]}


# --- insights ------------------------------------------------------------------------------------

def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def latest_eval(tag: str = "auto") -> dict | None:
    """A named run's summary, or (default) the most recent FULL run of the real system (from the catalog).

    "auto" skips ablated runs, partial runs, runs with fewer cases than the setting eval.full_run_min_cases and the
    preserved first-run copies, so the insights page describes the system as it is now.
    """
    from src.catalog import eval_store, settings
    if tag != "auto":
        r = eval_store.run(tag)
        return r["summary"] if r and r["status"] == "complete" and r["summary"] else None
    minimum = settings.get("eval.full_run_min_cases")
    for r in eval_store.runs("main"):                     # newest first
        s = r["summary"]
        if r["status"] != "complete" or not s or s.get("ablate") or s.get("n", 0) < minimum or "_run1_" in r["tag"]:
            continue
        return s
    return None


def metrics() -> dict:
    """Everything on the insights page. A number without a source is returned as null, never guessed."""
    with db.get_conn() as conn:
        latest = [dict(r) for r in conn.execute(
            "SELECT a.* FROM ai_results a JOIN (SELECT ticket_id, MAX(id) mid FROM ai_results GROUP BY ticket_id) m "
            "ON a.id = m.mid")]
        decisions = [dict(r) for r in conn.execute(
            "SELECT d.* FROM decisions d JOIN (SELECT ticket_id, MAX(id) mid FROM decisions GROUP BY ticket_id) m "
            "ON d.id = m.mid")]
        per_day = [dict(r) for r in conn.execute(
            "SELECT substr(created_at,1,10) day, COUNT(*) n, SUM(decision='ANSWER') answered, "
            "SUM(decision='ESCALATE') escalated FROM ai_results GROUP BY day ORDER BY day DESC LIMIT 14")]
    n = len(latest)
    answered = [r for r in latest if r["decision"] == "ANSWER"]
    llm = [r["latency_ms"] / 1000 for r in latest if (r["total_tokens"] or 0) > 0 and r["latency_ms"]]
    approved = [d for d in decisions if d["action"] in ("approve", "edit")]
    edited = [d for d in approved if d["action"] == "edit"]
    after, before = latest_eval("auto"), latest_eval("before")
    from src.catalog import eval_store
    second_run = eval_store.run("second_contact")
    second = second_run["summary"] if second_run else None
    cost = sum(r["cost_usd"] or 0 for r in latest)

    def rate(a: int, b: int):
        return round(a / b, 3) if b else None

    return {
        "tickets_processed": n,
        "ai_answer_rate": rate(len(answered), n),
        "ai_escalation_rate": rate(n - len(answered), n),
        "human_decisions": len(decisions),
        "edit_rate": rate(len(edited), len(approved)),
        "cost_per_answered_usd": round(cost / len(answered), 6) if answered else None,
        "latency_p50_s": round(statistics.median(llm), 1) if llm else None,
        "latency_p95_s": round(sorted(llm)[min(len(llm) - 1, int(0.95 * (len(llm) - 1) + 0.5))], 1) if llm else None,
        "second_contact": ({"deflection_rate": second.get("deflection_rate"), "simulated_reopen_rate": second.get("simulated_reopen_rate"),
                            "n": second.get("n")} if second else None),
        "eval": ({
            "n": after["n"], "pass_rate": after["pass_rate"], "tag": after["tag"],
            "superseded_final_rate": after["superseded_policy"]["final_rate"],
            "superseded_before": before["superseded_policy"]["final_rate"] if before else None,
            "judge_agreement": after["judge"]["agreement"].get("agreement") if after["judge"]["agreement"].get("n") else None,
            "judge_labels": after["judge"]["agreement"].get("n", 0),
            "cost_per_deflected_usd": after["cost_latency"]["cost_per_deflected_usd"],
            "failure_modes": [{"mode": k, "count": v["count"], "severity": v["severity"], "trace_id": v["trace_ids"][0]}
                              for k, v in after["failure_modes"].items()],
            "both_versions": after["both_versions"],
        } if after else None),
        "per_day": per_day,
    }

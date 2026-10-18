"""Tier-1 Deflection Assistant API. Thin: every decision comes from tier1.service.handle_ticket, so the
UI shows exactly what the eval suite graded.

Any signed-in user:  chat only -- ask as their OWN customer account (matched on email), poll the job,
                     articles (source drawer), report a wrong answer
Admin:               act as any customer in the chat, ticket queue and review, random ticket, decisions, escalations, insights, review inbox,
                     regression cases, eval runs, traces
"""
import logging
import os
import random
import re
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import UserOut, get_current_user, require_admin
from src.config import PROJECT_ROOT, VARIANT_A_CORPUS_DIR
from src.observability.redact import redact
from src.catalog import eval_store, ref
from tier1 import db, eval_cases, store, tracing_store
from tier1.models import TicketRequest

log = logging.getLogger("api.tier1")
router = APIRouter(prefix="/api/tier1", tags=["tier1"])

DEMO_CUSTOMER_ID = os.environ.get("TIER1_DEMO_CUSTOMER_ID", "").strip()
_slots_lock = threading.Lock()
_slots_holder: dict = {}


def _slots() -> threading.BoundedSemaphore:
    """Concurrent answer jobs (setting tier1.answer_slots, read once per process); the token limiter serialises the rest."""
    with _slots_lock:
        if "sem" not in _slots_holder:
            from src.catalog import settings
            _slots_holder["sem"] = threading.BoundedSemaphore(settings.get("tier1.answer_slots"))
        return _slots_holder["sem"]
_eval_runs: dict[str, dict] = {}
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,80}$")
_TAG = re.compile(r"^[a-z0-9_-]{1,20}$")


def _ready() -> None:
    db.seed_from_synthetic()
    tracing_store.install()


# --- queue and ticket -------------------------------------------------------------------------

@router.get("/tickets")
def tickets(status: str = "", q: str = "", policy: str = "", region: str = "", page: int = Query(1, ge=1),
            _admin: UserOut = Depends(require_admin)):
    _ready()
    return store.list_tickets(status=status, q=q, policy=policy, region=region, page=page)


@router.get("/tickets/{ticket_id}")
def ticket(ticket_id: str, _admin: UserOut = Depends(require_admin)):
    _ready()
    detail = store.ticket_detail(ticket_id)
    if detail is None:
        raise HTTPException(404, "Ticket not found")
    return detail


@router.get("/random-ticket")
def random_ticket(seed: int | None = None, _admin: UserOut = Depends(require_admin)):
    """A random draw from the whole sample. The seed is returned so the draw can be reproduced."""
    _ready()
    seed = seed if seed is not None else random.SystemRandom().randrange(1_000_000)
    with db.get_conn() as conn:
        ids = [r[0] for r in conn.execute("SELECT ticket_id FROM tickets ORDER BY ticket_id")]
    return {"seed": seed, "ticket_id": random.Random(seed).choice(ids)}


def _own_customer(user: UserOut) -> dict | None:
    """The customer a non-admin user is. Matched on the account email; TIER1_DEMO_CUSTOMER_ID is a demo-only
    fallback for when no real customer data is linked to the sign-in (leave it unset in production)."""
    from api.billing import repo
    row = repo.get_user_by_email(user.email)
    found = db.get_customer(row["customer_id"]) if row and row.get("customer_id") else None
    if found is None:
        found = db.customer_for_email(user.email)
    if found is None and DEMO_CUSTOMER_ID:
        found = db.get_customer(DEMO_CUSTOMER_ID)
    return found


@router.get("/me/customer")
def me_customer(user: UserOut = Depends(get_current_user)):
    """Which customer account the chat acts as for this user. Admins choose any customer, so they get null."""
    _ready()
    if user.role == "admin":
        return {"customer": None, "can_choose": True}
    c = _own_customer(user)
    if c is None:
        return {"customer": None, "can_choose": False}
    return {"customer": {"customer_id": c["customer_id"], "region": c["region"], "plan": c["plan"],
                         "policy_version": c["policy_version"]}, "can_choose": False}


@router.get("/customers")
def customers(_admin: UserOut = Depends(require_admin)):
    """Customers for the admin's act-as picker, masked, with their orders."""
    _ready()
    from tier1.masking import mask_name
    with db.get_conn() as conn:
        cust = [dict(r) for r in conn.execute("SELECT customer_id, name, region, plan, policy_version FROM customers ORDER BY customer_id")]
        orders = [dict(r) for r in conn.execute("SELECT order_id, customer_id, purchase_date FROM orders ORDER BY order_id")]
    by_cust: dict[str, list] = {}
    for o in orders:
        by_cust.setdefault(o["customer_id"], []).append({"order_id": o["order_id"], "purchase_date": o["purchase_date"],
                                                         "age_days": store._order_age(o["purchase_date"])})
    return [{**c, "name": mask_name(c["name"]), "orders": by_cust.get(c["customer_id"], [])[:6]} for c in cust]


# --- answer job -------------------------------------------------------------------------------

class AnswerRequest(BaseModel):
    ticket_id: str | None = None
    text: str | None = Field(None, max_length=4000)
    subject: str = Field("", max_length=300)
    customer_id: str | None = None
    order_id: str | None = None


@router.post("/answer")
def answer(req: AnswerRequest, user: UserOut = Depends(get_current_user)):
    _ready()
    ticket_id = ""
    if req.ticket_id:
        if user.role != "admin":
            raise HTTPException(403, "Only an admin can run a queued ticket")
        t = db.get_ticket(req.ticket_id)
        if t is None:
            raise HTTPException(404, "Ticket not found")
        treq = TicketRequest(body=t["body"], subject=t["subject"] or "", customer_id=t["customer_id"],
                             order_id=t["order_id"], ticket_id=t["ticket_id"])
        ticket_id = t["ticket_id"]
    elif req.text:
        if user.role == "admin":
            customer_id = req.customer_id
            order_id = req.order_id or ""
        else:
            own = _own_customer(user)
            if own is None:
                raise HTTPException(409, "No customer account is linked to your sign-in, so the assistant cannot look anything up.")
            if req.customer_id and req.customer_id != own["customer_id"]:
                raise HTTPException(403, "You can only ask about your own account")
            customer_id = own["customer_id"]
            order = db.get_order(req.order_id) if req.order_id else None
            order_id = order["order_id"] if order and order["customer_id"] == customer_id else ""
        if not customer_id:
            raise HTTPException(400, "Choose a customer")
        if db.get_customer(customer_id) is None:
            raise HTTPException(404, "Customer not found")
        treq = TicketRequest(body=req.text, subject=req.subject, customer_id=customer_id,
                             order_id=order_id, ticket_id="")
    else:
        raise HTTPException(400, "Provide ticket_id, or text with customer_id")

    if not _slots().acquire(blocking=False):
        raise HTTPException(429, "The assistant is busy with other tickets. Try again in a minute.")
    trace_id = uuid.uuid4().hex
    treq.trace_id = trace_id
    job_id = store.create_job(user.email, trace_id)

    def worker():
        try:
            resp = tier1_handle(treq, on_step=lambda step: store.append_step(job_id, redact(step)))
            result = resp.to_dict()
            if ticket_id:
                store.save_result(ticket_id, result)
            store.finish_job(job_id, result)
        except Exception as exc:
            log.error("tier1 job %s failed: %s", job_id, type(exc).__name__)
            store.fail_job(job_id, "The assistant could not finish this ticket. Escalate it to a person.")
        finally:
            _slots().release()

    threading.Thread(target=worker, daemon=True).start()
    return {"job_id": job_id, "trace_id": trace_id}


def tier1_handle(treq, on_step):
    from tier1.service import handle_ticket
    return handle_ticket(treq, on_step=on_step)


_USER_RESULT_KEYS = ("decision", "reason", "trace_id", "customer_reply", "citations", "entitlement", "sources")


def _public_result(result: dict | None) -> dict | None:
    """What a non-admin may see: the customer-facing answer and its sources, never the blocked draft,
    the guard findings or the handoff detail."""
    if result is None:
        return None
    return {k: result.get(k) for k in _USER_RESULT_KEYS}


@router.get("/jobs/{job_id}")
def job(job_id: str, user: UserOut = Depends(get_current_user)):
    found = store.get_job(job_id)
    if not found:
        raise HTTPException(404, "Job not found")
    if user.role != "admin":
        if found.get("owner") != user.email:
            raise HTTPException(404, "Job not found")
        found = {**found, "result": _public_result(found["result"])}
    return found


# --- human decision and feedback --------------------------------------------------------------

class DecisionRequest(BaseModel):
    action: str = Field(pattern="^(approve|edit|escalate|reject)$")
    text: str | None = Field(None, max_length=4000)


@router.post("/tickets/{ticket_id}/decision")
def decide(ticket_id: str, req: DecisionRequest, user: UserOut = Depends(require_admin)):
    _ready()
    if db.get_ticket(ticket_id) is None:
        raise HTTPException(404, "Ticket not found")
    if req.action == "escalate":
        ai = store.latest_result(ticket_id)
        db.create_handoff(ticket_id, "other", (req.text or "escalated by agent")[:1000], ai["trace_id"] if ai else None)
    return store.record_decision(ticket_id, req.action, req.text, user.email)


class FeedbackRequest(BaseModel):
    trace_id: str = Field(min_length=8, max_length=64)
    ticket_id: str | None = None
    reason: str
    comment: str | None = Field(None, max_length=500)


@router.post("/feedback")
def feedback(req: FeedbackRequest, user: UserOut = Depends(get_current_user)):
    _ready()
    if req.reason not in eval_cases.reasons():
        raise HTTPException(400, f"reason must be one of {eval_cases.reasons()}")
    return {"id": store.add_feedback(req.ticket_id, req.trace_id, req.reason, req.comment, user.email)}


@router.get("/feedback")
def feedback_inbox(status: str = "", _admin: UserOut = Depends(require_admin)):
    _ready()
    return store.list_feedback(status)


@router.post("/feedback/{feedback_id}/eval-case")
def feedback_to_case(feedback_id: int, _admin: UserOut = Depends(require_admin)):
    """The closed loop: a reported failure becomes a permanent regression case."""
    _ready()
    fb = store.get_feedback(feedback_id)
    if not fb:
        raise HTTPException(404, "Feedback not found")
    if not fb["ticket_id"]:
        raise HTTPException(400, "This report has no ticket, so it cannot become a case")
    try:
        case = eval_cases.add_regression_case(fb["ticket_id"], fb["trace_id"], fb["reason"], fb["comment"] or "", actor=_admin.email)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    store.link_feedback_case(feedback_id, case["case_id"])
    return {"case_id": case["case_id"], "expected_decision": case["expected_decision"]}


# --- escalations ------------------------------------------------------------------------------

@router.get("/escalations")
def escalations(status: str = "", _admin: UserOut = Depends(require_admin)):
    _ready()
    return store.list_escalations(status)


class EscalationStatus(BaseModel):
    status: str = Field(pattern="^(claimed|resolved)$")


@router.post("/escalations/{handoff_id}/status")
def escalation_status(handoff_id: str, req: EscalationStatus, user: UserOut = Depends(require_admin)):
    _ready()
    if not store.update_escalation(handoff_id, req.status, user.email):
        raise HTTPException(404, "Escalation not found")
    return {"handoff_id": handoff_id, "status": req.status}


# --- articles (source drawer) -----------------------------------------------------------------

_article_files: dict[str, Path] = {}


def _article_index() -> dict[str, Path]:
    if not _article_files:
        for path in sorted(Path(VARIANT_A_CORPUS_DIR).glob("*.md")):
            text = path.read_text(encoding="utf-8")
            if text.startswith("---"):
                meta = yaml.safe_load(text.split("---", 2)[1]) or {}
                _article_files[str(meta.get("slug") or path.stem)] = path
    return _article_files


@router.get("/articles/{slug}")
def article(slug: str, _user: UserOut = Depends(get_current_user)):
    if not _SLUG.match(slug):
        raise HTTPException(400, "Invalid slug")
    path = _article_index().get(slug)
    if path is None:
        raise HTTPException(404, "Article not found")
    _, front, body = path.read_text(encoding="utf-8").split("---", 2)
    meta = yaml.safe_load(front) or {}
    title = next((ln[2:].strip() for ln in body.splitlines() if ln.startswith("# ")), slug)
    return {"slug": slug, "title": title, "doc_type": meta.get("doc_type"), "policy_version": meta.get("policy_version"),
            "applies_to": meta.get("applies_to"), "last_updated": str(meta.get("last_updated")),
            "synthetic": bool(meta.get("synthetic")),
            "retired": bool(ref.meta("policy_version", meta.get("policy_version") or "none", "retired", False)),
            "body": body.strip()}


# --- admin: insights, traces, eval ------------------------------------------------------------

@router.get("/metrics")
def metrics(_admin: UserOut = Depends(require_admin)):
    _ready()
    from src.catalog import settings
    return {**store.metrics(), "agreement_target": settings.get("eval.agreement_target"),
            "min_labels": settings.get("eval.min_labels")}


@router.get("/rules")
def rules(_admin: UserOut = Depends(require_admin)):
    """The live answer-guard pattern for refund and delivery topics: the workspace blocks Approve on an edited draft
    that matches it without an entitlement check (the same rule the post-guard applies)."""
    from src.catalog import guards
    return {"claim_topics": guards.active_rules()["post"]["claim_topics"]}


@router.get("/traces/{trace_id}")
def trace(trace_id: str, _admin: UserOut = Depends(require_admin)):
    _ready()
    spans = tracing_store.get_spans(trace_id)
    if not spans:
        raise HTTPException(404, "No spans for this trace")
    return {"summary": tracing_store.summarize(spans), "spans": spans}


# --- admin: human labels for judge agreement ----------------------------------------------------
# The person labelling must not see the judge's verdict or the assertion results (they would anchor the label),
# so the queue carries only what a Tier-1 lead would see: the ticket, the account facts, the reply and its sources.

def _eval_rows(tag: str) -> list[dict]:
    if not _TAG.match(tag):
        raise HTTPException(400, "Invalid tag")
    if eval_store.run(tag) is None:
        raise HTTPException(404, f"No eval results for '{tag}'")
    return eval_store.results(tag)


def _labellable(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r.get("decision") == "ANSWER" and r.get("reply") and r.get("judge")]


@router.get("/labels/runs")
def label_runs(_admin: UserOut = Depends(require_admin)):
    """Eval runs that have judged answers, newest first: the runs a person can label."""
    out = []
    for r in eval_store.runs():
        if r["status"] != "complete" or not _TAG.match(r["tag"]):
            continue
        n = len(_labellable(eval_store.results(r["tag"])))
        if n:
            out.append({"tag": r["tag"], "answers": n})
    return out


@router.get("/labels/queue")
def label_queue(tag: str, _admin: UserOut = Depends(require_admin)):
    from evaluation.integrated import labels as human_labels
    data = human_labels.load()
    items = []
    for r in _labellable(_eval_rows(tag)):
        items.append({
            "case_id": r["case_id"], "subject": r.get("subject", ""), "body": r.get("body", ""),
            "reply": r.get("customer_reply") or r["reply"],
            "account_facts": {"entitlement": r.get("entitlement"), "order": r.get("order_facts")},
            "sources": [{"chunk_id": s.get("chunk_id"), "slug": s.get("slug"), "policy_version": s.get("policy_version"),
                         "text": s.get("text", "")} for s in r.get("sources", [])],
            "label": human_labels.label_for(r, data),
        })
    return {"tag": tag, "labeler": data["labeler"], "queue_experience": data["queue_experience"],
            "min_labels": human_labels.min_labels(), "target": human_labels.agreement_target(), "items": items}


class LabelRequest(BaseModel):
    tag: str
    label: str | None = Field(None, pattern="^(GOOD|NOT_GOOD)$")   # null = skip / clear


@router.post("/labels/{case_id}")
def set_label(case_id: str, req: LabelRequest, _admin: UserOut = Depends(require_admin)):
    from evaluation.integrated import labels as human_labels
    row = next((r for r in _labellable(_eval_rows(req.tag)) if r["case_id"] == case_id), None)
    if row is None:
        raise HTTPException(404, f"{case_id} has no judged answer in '{req.tag}'")
    data = human_labels.load()
    if not data["labeler"]:
        raise HTTPException(400, "Enter your name and queue experience before labelling")
    human_labels.set_label(case_id, row["reply"], req.label, req.tag, actor=_admin.email)
    return {"case_id": case_id, "label": req.label}


class LabelerRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    queue_experience: str = Field(min_length=2, max_length=200)


@router.put("/labels/labeler")
def set_labeler(req: LabelerRequest, _admin: UserOut = Depends(require_admin)):
    from evaluation.integrated import labels as human_labels
    data = human_labels.set_labeler(req.name, req.queue_experience, actor=_admin.email)
    return {"labeler": data["name"], "queue_experience": data["queue_experience"]}


@router.get("/labels/agreement")
def label_agreement(tag: str, _admin: UserOut = Depends(require_admin)):
    """Agreement is revealed only once enough labels exist; before that, only the count (so it cannot steer labelling)."""
    from evaluation.integrated import labels as human_labels
    rows = _labellable(_eval_rows(tag))
    data = human_labels.load()
    labelled = sum(1 for r in rows if human_labels.label_for(r, data))
    out = {"tag": tag, "labelled": labelled, "answers": len(rows), "min_labels": human_labels.min_labels()}
    if labelled < human_labels.min_labels():
        return {**out, "status": "locked"}
    judges = {}
    for key in ("judge", "judge_alt"):
        if any(r.get(key) for r in rows):
            first = next(r[key] for r in rows if r.get(key))
            judges[key] = {"version": first.get("version", "v3b-integrated"), "model": first.get("model"),
                           **human_labels.agreement(rows, key)}
    return {**out, "status": "measured", "judges": judges}


class EvalRunRequest(BaseModel):
    only: str | None = Field(None, pattern="^[a-z_]{1,20}$")
    tag: str = "ui"
    cases: str = Field("main", pattern="^(main|regression)$")
    case_id: str | None = Field(None, pattern="^[A-Z]{2,4}[0-9]{2,3}$")


@router.post("/eval/run")
def eval_run(req: EvalRunRequest, _admin: UserOut = Depends(require_admin)):
    """Run the integrated eval suite in a separate process and report red or green when it ends."""
    if not _TAG.match(req.tag):
        raise HTTPException(400, "Invalid tag")
    if any(r["status"] == "running" for r in _eval_runs.values()):
        raise HTTPException(409, "An eval run is already in progress")
    run_id = uuid.uuid4().hex[:10]
    out_dir = store.EVAL_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"run_{run_id}.log"
    cmd = [sys.executable, "-u", "-m", "tier1", "eval", "--tag", req.tag, "--no-judge", "--cases", req.cases]
    cmd += (["--only", req.only] if req.only else []) + (["--case-id", req.case_id] if req.case_id else [])
    proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), stdout=log_path.open("w", encoding="utf-8"), stderr=subprocess.STDOUT)
    _eval_runs[run_id] = {"proc": proc, "tag": req.tag, "log": log_path, "status": "running"}
    return {"run_id": run_id}


@router.get("/eval/runs/{run_id}")
def eval_status(run_id: str, _admin: UserOut = Depends(require_admin)):
    run = _eval_runs.get(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    code = run["proc"].poll()
    run["status"] = "running" if code is None else ("done" if code == 0 else "failed")
    tail = run["log"].read_text(encoding="utf-8", errors="replace").splitlines()[-12:]
    summary = store.latest_eval(run["tag"]) if run["status"] == "done" else None
    cases = None
    if summary and summary["n"] <= 5:   # a single regression case: show each check, red or green
        cases = [{"case_id": r["case_id"], "passed": r["passed"], "decision": r["decision"], "trace_id": r["trace_id"],
                  "checks": r["checks"], "failed_checks": r["failed_checks"]} for r in _eval_rows(run["tag"])]
    return {"run_id": run_id, "status": run["status"], "cases": cases,
            "log_tail": [ln for ln in tail if ln.startswith("[") or ln.startswith("passed")],
            "summary": {"n": summary["n"], "passed": summary["passed"], "pass_rate": summary["pass_rate"],
                        "failure_modes": list(summary["failure_modes"])} if summary else None}

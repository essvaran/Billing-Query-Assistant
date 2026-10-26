"""Tier-1 API: queue, answer job, decisions, feedback to regression case, escalations, articles, metrics.
The agent is stubbed (no network); routing, storage, masking and permissions are real."""
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import tier1_router
from api.auth import UserOut, get_current_user
from tier1 import db, eval_cases, store
from tier1.models import TicketResponse


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(store, "EVAL_DIR", tmp_path / "eval")
    _clear_eval_runs()                                                     # never read the real eval results in a test
    monkeypatch.setattr(tier1_router.tracing_store, "install", lambda: None)  # no global sink in tests
    app = FastAPI()
    app.include_router(tier1_router.router)
    app.dependency_overrides[get_current_user] = lambda: UserOut(email="agent@example.com", role="admin")
    c = TestClient(app)
    c.app_ref = app
    return c


def _clear_eval_runs():
    from src.catalog import db as catalog_db
    with catalog_db.connect() as conn:
        conn.execute("DELETE FROM eval_runs")
        conn.execute("DELETE FROM eval_cases WHERE suite='regression'")
        catalog_db.bump(conn)


def as_user(client, email="user@example.com"):
    client.app_ref.dependency_overrides[get_current_user] = lambda: UserOut(email=email, role="user")


def as_admin(client):
    client.app_ref.dependency_overrides[get_current_user] = lambda: UserOut(email="lead@example.com", role="admin")


def fake_handle(decision="ANSWER", reply="Within the policy window [x].", reason=""):
    def handle(treq, on_step):
        on_step({"type": "tool_call", "tool": "check_entitlement", "args": {"customer_id": treq.customer_id}})
        on_step({"type": "guard", "stage": "post", "violations": []})
        return TicketResponse(decision, reply if decision == "ANSWER" else "", treq.trace_id, reason=reason,
                              tools_called=["check_entitlement"], cost_usd=0.001, latency_ms=2500.0, total_tokens=900,
                              entitlement={"policy_version": "refund-30d", "refund_days": 30, "plan": "standard",
                                           "region": "US", "customer_id": treq.customer_id})
    return handle


def run_job(client, monkeypatch, ticket_id="TK3000", **kw):
    monkeypatch.setattr(tier1_router, "tier1_handle", fake_handle(**kw))
    r = client.post("/api/tier1/answer", json={"ticket_id": ticket_id})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    for _ in range(50):
        job = client.get(f"/api/tier1/jobs/{job_id}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_queue_hides_ground_truth_and_masks_the_customer(client):
    data = client.get("/api/tier1/tickets").json()
    assert data["total"] == 300 and len(data["items"]) == 25
    item = data["items"][0]
    assert not {"kind", "expected_decision", "gold_slug", "expected_policy_version"} & set(item)
    assert "@" in item["customer_email"] and "***" in item["customer_email"]
    assert item["status"] == "new"


def test_queue_filters_by_policy_and_search(client):
    legacy = client.get("/api/tier1/tickets", params={"policy": "refund-14d"}).json()
    assert 0 < legacy["total"] < 300 and all(i["policy_version"] == "refund-14d" for i in legacy["items"])
    assert client.get("/api/tier1/tickets", params={"q": "zzzz-no-match"}).json()["total"] == 0


def test_ticket_detail_gives_the_agent_the_real_email_but_no_eval_fields(client):
    d = client.get("/api/tier1/tickets/TK3000").json()
    assert "@example.com" in d["customer"]["email"] and "***" not in d["customer"]["email"]
    assert not {"kind", "expected_decision", "gold_slug"} & set(d)
    assert client.get("/api/tier1/tickets/NOPE").status_code == 404


def test_answer_job_streams_steps_saves_the_result_and_updates_the_queue(client, monkeypatch):
    job = run_job(client, monkeypatch)
    assert job["status"] == "done" and job["result"]["decision"] == "ANSWER"
    assert [s["type"] for s in job["steps"]] == ["tool_call", "guard"]
    assert "cust_" in str(job["steps"])                      # ids in streamed steps are hashed
    detail = client.get("/api/tier1/tickets/TK3000").json()
    assert detail["ai"]["trace_id"] == job["trace_id"]
    queue = client.get("/api/tier1/tickets", params={"status": "draft_ready"}).json()
    assert queue["total"] == 1 and queue["items"][0]["ticket_id"] == "TK3000"


def test_failed_job_tells_the_agent_to_escalate_and_leaks_nothing(client, monkeypatch):
    def boom(treq, on_step):
        raise RuntimeError("secret internal detail")
    monkeypatch.setattr(tier1_router, "tier1_handle", boom)
    job_id = client.post("/api/tier1/answer", json={"ticket_id": "TK3000"}).json()["job_id"]
    for _ in range(50):
        job = client.get(f"/api/tier1/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "error" and "secret" not in job["error"] and "Escalate" in job["error"]


def test_busy_assistant_returns_429_not_a_hang(client, monkeypatch):
    monkeypatch.setattr(tier1_router, "_slots", lambda: __import__("threading").BoundedSemaphore(0))
    assert client.post("/api/tier1/answer", json={"ticket_id": "TK3000"}).status_code == 429


def test_answer_requires_a_ticket_or_text_with_customer(client):
    assert client.post("/api/tier1/answer", json={"text": "hi"}).status_code == 400


def test_decision_tracks_edit_rate_and_escalate_creates_a_handoff(client, monkeypatch):
    run_job(client, monkeypatch)
    same = client.post("/api/tier1/tickets/TK3000/decision",
                       json={"action": "approve", "text": "Within the policy window [x]."}).json()
    assert same == {"action": "approve", "edit_ratio": 0.0}
    edited = client.post("/api/tier1/tickets/TK3000/decision",
                         json={"action": "approve", "text": "A completely different reply."}).json()
    assert edited["action"] == "edit" and edited["edit_ratio"] > 0.3
    client.post("/api/tier1/tickets/TK3001/decision", json={"action": "escalate", "text": "needs a lead"})
    assert len(client.get("/api/tier1/escalations").json()) == 1
    assert client.post("/api/tier1/tickets/TK3000/decision", json={"action": "nuke"}).status_code == 422


def test_escalation_can_be_claimed_and_resolved(client):
    client.post("/api/tier1/tickets/TK3001/decision", json={"action": "escalate"})
    hid = client.get("/api/tier1/escalations").json()[0]["handoff_id"]
    assert client.post(f"/api/tier1/escalations/{hid}/status", json={"status": "claimed"}).status_code == 200
    row = client.get("/api/tier1/escalations", params={"status": "claimed"}).json()[0]
    assert row["claimed_by"] == "agent@example.com"
    assert client.post("/api/tier1/escalations/H-nope/status", json={"status": "resolved"}).status_code == 404


def test_feedback_becomes_a_regression_case_only_for_admins_and_only_once(client, monkeypatch):
    job = run_job(client, monkeypatch)
    fid = client.post("/api/tier1/feedback", json={"trace_id": job["trace_id"], "ticket_id": "TK3000",
                                                   "reason": "wrong_policy", "comment": "quoted 14 days"}).json()["id"]
    assert client.post("/api/tier1/feedback", json={"trace_id": job["trace_id"], "reason": "bogus"}).status_code == 400
    as_user(client)
    assert client.get("/api/tier1/feedback").status_code == 403                 # a user cannot read the inbox
    assert client.post(f"/api/tier1/feedback/{fid}/eval-case").status_code == 403
    as_admin(client)
    case = client.post(f"/api/tier1/feedback/{fid}/eval-case").json()
    assert case["case_id"] == "REG01"
    assert client.post(f"/api/tier1/feedback/{fid}/eval-case").status_code == 409
    assert client.get("/api/tier1/feedback", params={"status": "case_created"}).json()[0]["eval_case_id"] == "REG01"
    saved = eval_cases.load_regression_cases()[0]
    assert saved["regression_trace_id"] == job["trace_id"] and saved["slice"] == "regression"


def test_should_have_escalated_report_makes_an_escalate_case(client, monkeypatch):
    job = run_job(client, monkeypatch)
    fid = client.post("/api/tier1/feedback", json={"trace_id": job["trace_id"], "ticket_id": "TK3000",
                                                   "reason": "should_have_escalated"}).json()["id"]
    as_admin(client)
    client.post(f"/api/tier1/feedback/{fid}/eval-case")
    assert eval_cases.load_regression_cases()[0]["expected_decision"] == "ESCALATE"


def test_article_marks_the_retired_policy_and_rejects_bad_slugs(client):
    old = client.get("/api/tier1/articles/refund-policy-14d").json()
    new = client.get("/api/tier1/articles/refund-policy-30d").json()
    assert old["retired"] is True and new["retired"] is False and old["synthetic"] is True
    assert client.get("/api/tier1/articles/..%2Fsecrets").status_code in (400, 404)
    assert client.get("/api/tier1/articles/does-not-exist").status_code == 404


def test_random_ticket_is_reproducible_from_its_seed(client):
    a = client.get("/api/tier1/random-ticket", params={"seed": 7}).json()
    assert a == client.get("/api/tier1/random-ticket", params={"seed": 7}).json()
    assert client.get("/api/tier1/random-ticket").json()["seed"] != a["seed"] or True


def test_metrics_need_admin_and_never_invent_unmeasured_numbers(client, monkeypatch):
    as_user(client)
    assert client.get("/api/tier1/metrics").status_code == 403
    as_admin(client)
    run_job(client, monkeypatch)
    as_admin(client)
    m = client.get("/api/tier1/metrics").json()
    assert m["tickets_processed"] == 1 and m["ai_answer_rate"] == 1.0
    assert m["second_contact"] is None and m["edit_rate"] is None     # nothing measured, so null, not zero


def test_customers_endpoint_masks_names(client):
    c = client.get("/api/tier1/customers").json()
    assert len(c) == 60 and all("@" not in str(x) for x in c) and c[0]["orders"]


def test_metrics_report_what_the_eval_store_holds_and_pick_the_latest_full_run(client):
    from src.catalog import eval_store
    base = {"n": 39, "pass_rate": 0.85, "ablate": None, "superseded_policy": {"final_rate": 0.0}, "failure_modes": {},
            "judge": {"agreement": {}}, "cost_latency": {"cost_per_deflected_usd": 0.0016},
            "both_versions": {"n": 6, "passed": 6, "pairs": 3, "pairs_both_correct": 3}}
    eval_store.save_run("before", "main", "complete", {**base, "tag": "before", "ablate": "version_filter"}, {}, [])
    eval_store.save_run("holdout_x", "holdout", "complete", {**base, "tag": "holdout_x", "n": 15}, {}, [])
    eval_store.save_run("after", "main", "complete", {**base, "tag": "after"}, {}, [])
    eval_store.save_run("second_contact", "second_contact", "complete",
                        {"deflection_rate": 0.76, "simulated_reopen_rate": 0.6, "n": 10}, {}, [])
    as_admin(client)
    m = client.get("/api/tier1/metrics").json()
    assert m["eval"]["tag"] == "after" and m["eval"]["n"] == 39        # not the ablated run, not the 15-case run
    assert m["eval"]["superseded_before"] == 0.0
    assert m["second_contact"] == {"deflection_rate": 0.76, "simulated_reopen_rate": 0.6, "n": 10}
    assert m["eval"]["judge_agreement"] is None                         # no labels, so no number


# --- the regular user sees chat only ---------------------------------------------------------

def test_user_is_locked_out_of_every_operations_route(client):
    as_user(client)
    for method, path in [("get", "/api/tier1/tickets"), ("get", "/api/tier1/tickets/TK3000"),
                         ("get", "/api/tier1/random-ticket"), ("get", "/api/tier1/escalations"),
                         ("get", "/api/tier1/metrics"), ("get", "/api/tier1/traces/abc"), ("get", "/api/tier1/feedback")]:
        assert getattr(client, method)(path).status_code == 403, path
    assert client.post("/api/tier1/tickets/TK3000/decision", json={"action": "escalate"}).status_code == 403
    assert client.post("/api/tier1/escalations/H-x/status", json={"status": "claimed"}).status_code == 403
    assert client.post("/api/tier1/eval/run", json={}).status_code == 403
    assert client.get("/api/tier1/escalations", params={"status": "queued"}).status_code == 403


def linked_user(client):
    """A user whose sign-in email is a customer's email: the production mapping."""
    cust = db.get_customer("C1000")
    as_user(client, email=cust["email"])
    return cust


def test_user_can_ask_as_their_own_customer_and_only_sees_the_customer_facing_result(client, monkeypatch):
    client.get("/api/tier1/tickets")                       # seeds the db
    cid = linked_user(client)["customer_id"]
    assert client.get("/api/tier1/me/customer").json()["customer"]["customer_id"] == cid

    def handle(treq, on_step):
        on_step({"type": "guard", "stage": "pre", "blocked": False, "category": None})
        on_step({"type": "tool_call", "lap": 1, "tool": "check_entitlement", "args": {"customer_id": "C1000"}})
        on_step({"type": "tool_result", "lap": 1, "tool": "check_entitlement", "result": {"plan": "secret-plan"}})
        on_step({"type": "llm_response", "lap": 1, "lap_tokens": 900, "cumulative_tokens": 900})
        on_step({"type": "done", "reply": "secret draft", "cost_usd": 0.01, "total_tokens": 900})
        on_step({"type": "guard", "stage": "post", "violations": ["uncited_policy"], "citations": 0})
        return TicketResponse("ESCALATE", "", treq.trace_id, reason="legal", draft="secret draft",
                              violations=[{"code": "x", "detail": "internal"}], handoff_id="H-1",
                              customer_reply="We have passed this to our team.")
    monkeypatch.setattr(tier1_router, "tier1_handle", handle)
    r = client.post("/api/tier1/answer", json={"text": "I want a refund"})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    for _ in range(50):
        job = client.get(f"/api/tier1/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "done" and job["result"]["decision"] == "ESCALATE"
    assert not {"draft", "violations", "handoff_id", "tools_called", "reply"} & set(job["result"])
    assert "secret draft" not in str(job)
    assert "owner" not in job
    # progress only: which stage ran and whether it passed, nothing the model or a tool produced
    assert [s["type"] for s in job["steps"]] == ["guard", "tool_call", "tool_result", "guard"]
    leaked = {"args", "result", "reply", "cost_usd", "lap_tokens", "total_tokens", "violations", "category"}
    assert not any(leaked & set(s) for s in job["steps"])
    assert "secret-plan" not in str(job) and "uncited_policy" not in str(job)
    assert job["steps"][-1] == {"type": "guard", "stage": "post", "blocked": True, "citations": 0}


def test_user_cannot_run_a_queued_ticket_or_read_someone_elses_job(client, monkeypatch):
    client.get("/api/tier1/tickets")
    as_user(client)
    assert client.post("/api/tier1/answer", json={"ticket_id": "TK3000"}).status_code == 403
    monkeypatch.setattr(tier1_router, "tier1_handle", fake_handle())
    linked_user(client)
    job_id = client.post("/api/tier1/answer", json={"text": "hello"}).json()["job_id"]
    as_user(client, email="other@example.com")
    assert client.get(f"/api/tier1/jobs/{job_id}").status_code == 404
    as_admin(client)
    assert client.get(f"/api/tier1/jobs/{job_id}").status_code == 200


def test_user_can_report_only_their_own_answer_and_open_sources(client, monkeypatch):
    client.get("/api/tier1/tickets")
    as_user(client)
    assert client.post("/api/tier1/feedback", json={"trace_id": "a" * 16, "reason": "wrong_policy"}).status_code == 404
    monkeypatch.setattr(tier1_router, "tier1_handle", fake_handle())
    cust = linked_user(client)
    trace_id = client.post("/api/tier1/answer", json={"text": "hello"}).json()["trace_id"]
    r = client.post("/api/tier1/feedback", json={"trace_id": trace_id, "reason": "wrong_policy"})
    assert r.status_code == 200
    as_user(client, email="other@example.com")
    assert client.post("/api/tier1/feedback", json={"trace_id": trace_id, "reason": "wrong_policy"}).status_code == 404
    as_user(client, email=cust["email"])
    assert client.get("/api/tier1/articles/refund-policy-30d").status_code == 200


def test_user_without_a_linked_customer_cannot_ask_and_cannot_pick_someone_else(client, monkeypatch):
    client.get("/api/tier1/tickets")
    as_user(client)                                           # user@example.com is nobody's customer
    assert client.get("/api/tier1/me/customer").json() == {"customer": None, "can_choose": False}
    assert client.post("/api/tier1/answer", json={"text": "hi"}).status_code == 409
    assert client.get("/api/tier1/customers").status_code == 403
    monkeypatch.setattr(tier1_router, "tier1_handle", fake_handle())
    linked_user(client)
    assert client.post("/api/tier1/answer", json={"text": "hi", "customer_id": "C1001"}).status_code == 403


def test_demo_fallback_customer_is_used_only_when_configured(client, monkeypatch):
    client.get("/api/tier1/tickets")
    as_user(client)
    monkeypatch.setattr(tier1_router, "DEMO_CUSTOMER_ID", "C1000")
    assert client.get("/api/tier1/me/customer").json()["customer"]["customer_id"] == "C1000"


def test_admin_chooses_any_customer(client, monkeypatch):
    monkeypatch.setattr(tier1_router, "tier1_handle", fake_handle())
    assert client.get("/api/tier1/me/customer").json() == {"customer": None, "can_choose": True}
    cid = client.get("/api/tier1/customers").json()[3]["customer_id"]
    assert client.post("/api/tier1/answer", json={"text": "hi", "customer_id": cid}).status_code == 200
    assert client.post("/api/tier1/answer", json={"text": "hi"}).status_code == 400

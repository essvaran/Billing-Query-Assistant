"""The admin labelling page's API: the judge's verdict never reaches the labeller, and agreement stays locked
until enough labels exist."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import tier1_router
from api.auth import UserOut, get_current_user
from evaluation.integrated import labels as human_labels
from tier1 import store


def _row(cid, verdict="GOOD", decision="ANSWER"):
    return {"case_id": cid, "decision": decision, "passed": True, "subject": "Refund", "body": "Can I get a refund?",
            "reply": f"Raw reply {cid} [KB-1]", "customer_reply": f"Reply {cid} [1]\n\nSources:\n[1] refund-policy-30d",
            "entitlement": {"policy_version": "refund-30d"}, "order_facts": None,
            "sources": [{"chunk_id": "KB-1", "slug": "refund-policy-30d", "policy_version": "refund-30d", "text": "30 days"}],
            "checks": {"cites_gold_source": False}, "failed_checks": [{"name": "cites_gold_source", "detail": "x"}],
            "judge": {"verdict": verdict, "reason": "secret reasoning", "model": "m", "version": "week6-v2r"},
            "judge_alt": {"verdict": verdict, "model": "m2", "version": "v3b-integrated"}}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from src.catalog import db as catalog_db, eval_store
    with catalog_db.connect() as conn:                      # only this test's run, no imported history, no old labels
        conn.execute("DELETE FROM eval_runs")
        conn.execute("DELETE FROM eval_labels")
        conn.execute("DELETE FROM catalog_meta WHERE key='labeler'")
        catalog_db.bump(conn)
    rows = [_row(f"C{i:02d}") for i in range(22)] + [_row("ESC", decision="ESCALATE")]
    eval_store.save_run("run1", "main", "complete", {}, {}, rows)
    monkeypatch.setattr(store, "EVAL_DIR", tmp_path / "eval")
    app = FastAPI()
    app.include_router(tier1_router.router)
    app.dependency_overrides[get_current_user] = lambda: UserOut(email="lead@example.com", role="admin")
    c = TestClient(app)
    c.app_ref = app
    return c


def test_runs_list_only_runs_with_judged_answers(client):
    assert client.get("/api/tier1/labels/runs").json() == [{"tag": "run1", "answers": 22}]


def test_queue_hides_the_judge_and_the_assertions(client):
    body = client.get("/api/tier1/labels/queue", params={"tag": "run1"}).json()
    assert len(body["items"]) == 22                      # the escalation is not labelled
    text = json.dumps(body)
    for leak in ("secret reasoning", "verdict", "judge", "cites_gold_source", "failed_checks"):
        assert leak not in text
    item = body["items"][0]
    assert item["reply"].startswith("Reply C00 [1]")     # the customer-facing text, not raw chunk ids
    assert item["sources"][0]["slug"] == "refund-policy-30d" and item["label"] is None


def test_labeller_must_identify_themselves_first(client):
    r = client.post("/api/tier1/labels/C00", json={"tag": "run1", "label": "GOOD"})
    assert r.status_code == 400
    assert client.put("/api/tier1/labels/labeler", json={"name": "Sam Lee", "queue_experience": "2 years Tier-1"}).status_code == 200
    assert client.post("/api/tier1/labels/C00", json={"tag": "run1", "label": "GOOD"}).status_code == 200
    assert client.get("/api/tier1/labels/queue", params={"tag": "run1"}).json()["items"][0]["label"] == "GOOD"


def test_bad_values_unknown_cases_and_bad_tags_are_refused(client):
    client.put("/api/tier1/labels/labeler", json={"name": "Sam Lee", "queue_experience": "2 years"})
    assert client.post("/api/tier1/labels/C00", json={"tag": "run1", "label": "MAYBE"}).status_code == 422
    assert client.post("/api/tier1/labels/ESC", json={"tag": "run1", "label": "GOOD"}).status_code == 404
    assert client.get("/api/tier1/labels/queue", params={"tag": "../x"}).status_code == 400


def test_agreement_is_locked_until_the_minimum_then_reported_per_judge(client):
    client.put("/api/tier1/labels/labeler", json={"name": "Sam Lee", "queue_experience": "2 years"})
    for i in range(19):
        client.post(f"/api/tier1/labels/C{i:02d}", json={"tag": "run1", "label": "GOOD"})
    locked = client.get("/api/tier1/labels/agreement", params={"tag": "run1"}).json()
    assert locked["status"] == "locked" and locked["labelled"] == 19 and "judges" not in locked
    client.post("/api/tier1/labels/C19", json={"tag": "run1", "label": "NOT_GOOD"})
    ag = client.get("/api/tier1/labels/agreement", params={"tag": "run1"}).json()
    assert ag["status"] == "measured"
    assert ag["judges"]["judge"]["n"] == 20 and ag["judges"]["judge"]["agree"] == 19
    assert ag["judges"]["judge"]["version"] == "week6-v2r" and "judge_alt" in ag["judges"]


def test_labelling_is_admin_only(client):
    client.app_ref.dependency_overrides[get_current_user] = lambda: UserOut(email="u@example.com", role="user")
    assert client.get("/api/tier1/labels/runs").status_code == 403
    assert client.post("/api/tier1/labels/C00", json={"tag": "run1", "label": "GOOD"}).status_code == 403


def test_a_single_regression_case_run_reports_each_check(client, tmp_path):
    from src.catalog import eval_store
    row = {"case_id": "REG01", "passed": False, "decision": "ANSWER", "trace_id": "t1",
           "checks": {"cites_gold_source": False, "decision_matches": True},
           "failed_checks": [{"name": "cites_gold_source", "detail": "wanted a, cited b"}]}
    eval_store.save_run("reg_reg01", "regression", "complete",
                        {"n": 1, "passed": 0, "pass_rate": 0.0, "failure_modes": {"wrong_source_cited": {}}}, {}, [row])
    log = tmp_path / "run.log"
    log.write_text("[ 1/1] FAIL REG01\n", encoding="utf-8")

    class Done:
        def poll(self):
            return 0
    tier1_router._eval_runs["r1"] = {"proc": Done(), "tag": "reg_reg01", "log": log, "status": "running"}
    body = client.get("/api/tier1/eval/runs/r1").json()
    assert body["status"] == "done" and body["summary"]["passed"] == 0
    assert body["cases"][0]["case_id"] == "REG01" and body["cases"][0]["checks"]["cites_gold_source"] is False
    tier1_router._eval_runs.pop("r1")


def test_run_request_accepts_one_regression_case_and_rejects_bad_ids(client, monkeypatch, tmp_path):
    started = {}

    class FakeProc:
        def poll(self):
            return None
    monkeypatch.setattr(store, "EVAL_DIR", tmp_path)
    monkeypatch.setattr(tier1_router.subprocess, "Popen", lambda cmd, **kw: started.setdefault("cmd", cmd) and FakeProc())
    r = client.post("/api/tier1/eval/run", json={"cases": "regression", "case_id": "REG01", "tag": "reg_reg01"})
    assert r.status_code == 200
    assert started["cmd"][-4:] == ["--cases", "regression", "--case-id", "REG01"]
    tier1_router._eval_runs.clear()
    assert client.post("/api/tier1/eval/run", json={"cases": "regression", "case_id": "x; rm -rf /"}).status_code == 422

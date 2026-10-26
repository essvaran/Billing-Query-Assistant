"""Tests for the observability API, eval runner, feedback and the Langfuse-backed trace store.

Traces live only in Langfuse, so these tests use a fake Langfuse client that mimics the real API
(server-side filters, paging, 404 and 429 errors). SQLite is a temporary file; the eval set is temporary.
"""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api.database as database
from auth_helpers import session_token as _make_jwt
from api.main import app
from src.generation import langfuse_client
from src.observability import alerting, demo, email_template, eval_runner, trace_store

REFUSAL = "I don't have enough information to answer that. For further help, please contact our support team."
BAD = "Yes, you are entitled to a full refund within 30 days. [HC-BILL-006--a--b]"
BAD_ID, OK_ID, REFUSAL_ID = "t-bad-0001", "t-ok-0001", "t-refusal-1"

_now = datetime.now(timezone.utc)
DAY = (_now - timedelta(days=2)).strftime("%Y-%m-%d")
YESTERDAY_TS = (_now - timedelta(days=1)).replace(microsecond=0).isoformat()


def _trace(trace_id, ts, question="Can I get a refund?", answer=REFUSAL, valid=False, version="v1",
           cost=0.0001, gen_ms=1000.0, tokens_in=900, tokens_out=100, user=None):
    return {
        "trace_id": trace_id, "timestamp": ts, "question": question, "prompt_version": version,
        "model": "openai/gpt-oss-120b", "temperature": 0.0, "retriever": "hybrid", "top_k": 3,
        "collection": "c", "retrieved_chunks": [{"chunk_id": "A--b--c", "score": 0.03, "rank": 1}],
        "raw_output": answer, "final_answer": answer, "citations": [], "citations_valid": valid,
        "retrieval_ms": 40.0, "generation_ms": gen_ms, "total_ms": 40.0 + gen_ms,
        "input_tokens": tokens_in, "output_tokens": tokens_out, "cost_usd": cost, "error": None,
        "user_email": user,
    }


class FakeApiError(Exception):
    def __init__(self, status_code, body=None):
        super().__init__(f"status {status_code}")
        self.status_code, self.body = status_code, body


class FakeTraceHandle:
    def __init__(self, store, kwargs):
        self.store, self.kwargs, self.updates, self.generations = store, kwargs, [], []

    def update(self, **kwargs):
        self.updates.append(kwargs)

    def generation(self, **kwargs):
        self.generations.append(kwargs)

    def span(self, **kwargs):
        return SimpleNamespace(end=lambda **k: None)


class FakeLangfuse:
    """Mimics the Langfuse v2 SDK reads and writes this app uses."""

    def __init__(self):
        self.traces = {}
        self.fetch_calls, self.fetch_trace_calls, self.created, self.scores = [], [], [], []
        self.fail_with = None

    def add(self, record, old_style=False):
        meta = {"prompt_version": record["prompt_version"], "model": record["model"]}
        if not old_style:
            meta.update({k: record[k] for k in (
                "retriever", "collection", "top_k", "temperature", "citations_valid", "citations", "retrieved_chunks",
                "retrieval_ms", "generation_ms", "total_ms", "input_tokens", "output_tokens", "cost_usd")})
        when = datetime.fromisoformat(record["timestamp"])
        self.traces[record["trace_id"]] = SimpleNamespace(
            id=record["trace_id"], timestamp=when, name="answer_question", user_id=record.get("user_email"),
            version=record["prompt_version"], tags=[f"prompt:{record['prompt_version']}"],
            input={"question": record["question"]}, output={"final_answer": record["final_answer"]},
            metadata=meta, latency=(record["total_ms"] or 0) / 1000, total_cost=record["cost_usd"], scores=[])

    def fetch_traces(self, page=None, limit=None, user_id=None, name=None, session_id=None, from_timestamp=None,
                     to_timestamp=None, environment=None, order_by=None, tags=None):
        self.fetch_calls.append({"page": page, "limit": limit, "user_id": user_id, "name": name,
                                 "from_timestamp": from_timestamp, "to_timestamp": to_timestamp, "tags": tags})
        if self.fail_with:
            raise self.fail_with
        rows = sorted(self.traces.values(), key=lambda t: t.timestamp, reverse=True)
        rows = [t for t in rows if (not name or t.name == name) and (not user_id or t.user_id == user_id)
                and (not from_timestamp or t.timestamp >= from_timestamp)
                and (not to_timestamp or t.timestamp <= to_timestamp)
                and (not tags or all(tag in t.tags for tag in tags))]
        page, limit = page or 1, limit or 50
        window = rows[(page - 1) * limit: page * limit]
        meta = SimpleNamespace(page=page, limit=limit, total_items=len(rows), total_pages=max(1, -(-len(rows) // limit)))
        return SimpleNamespace(data=window, meta=meta)

    def fetch_trace(self, id):
        self.fetch_trace_calls.append(id)
        if self.fail_with:
            raise self.fail_with
        if id not in self.traces:
            raise FakeApiError(404, {"message": "not found"})
        return SimpleNamespace(data=self.traces[id])

    def trace(self, **kwargs):
        handle = FakeTraceHandle(self, kwargs)
        self.created.append(handle)
        return handle

    def score(self, **kwargs):
        self.scores.append(kwargs)

    def flush(self):
        pass


@pytest.fixture
def fake(monkeypatch):
    store = FakeLangfuse()
    monkeypatch.setattr(langfuse_client, "_langfuse", store)
    monkeypatch.setenv("LANGFUSE_API_MAX_PER_MIN", "1000")
    trace_store.clear_cache()
    yield store
    trace_store.clear_cache()


@pytest.fixture
def client(tmp_path, monkeypatch, fake):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test.db")
    database.init_db()
    from src.catalog import db as catalog_db, eval_store
    with catalog_db.connect() as conn:                       # the Docs suite holds only this test's case
        conn.execute("DELETE FROM eval_cases WHERE suite='docs'")
        catalog_db.bump(conn)
    eval_store.save_case("G01", "docs", {"question": "Can I get a refund?", "mode": "corpus_gap",
                                          "expected_behavior": "refusal"}, "test", create=True)
    monkeypatch.setattr(eval_runner, "_current_prompt_version", lambda: "vtest")
    for key in ("ALERT_EMAIL_FROM", "ALERT_EMAIL_TO", "ALERT_EMAIL_PASSWORD", "OBS_DEMO_TOOLS"):
        monkeypatch.delenv(key, raising=False)
    fake.add(_trace(BAD_ID, f"{DAY}T14:32:17+00:00", answer=BAD, valid=False, user="alice@example.com"))
    fake.add(_trace(OK_ID, f"{DAY}T09:00:00+00:00", question="What is ERR-4032?",
                    answer="It means X. [A--b--c]", valid=True, version="v2", user="bob@example.com"))
    fake.add(_trace(REFUSAL_ID, YESTERDAY_TS, valid=False, version="v2", user="alice@example.com"))
    return TestClient(app)


def admin():
    return {"Authorization": "Bearer " + _make_jwt("admin@example.com", "admin")}


def user():
    return {"Authorization": "Bearer " + _make_jwt("user@example.com", "user")}


def test_requires_admin(client):
    assert client.get("/api/obs/meta").status_code == 401
    assert client.get("/api/obs/meta", headers=user()).status_code == 403
    assert client.get("/api/obs/meta", headers=admin()).status_code == 200


def test_drill_slice_finds_only_the_bad_trace(client):
    r = client.get("/api/obs/traces", headers=admin(), params={
        "after": f"{DAY}T12:00:00Z", "before": f"{DAY}T18:00:00Z", "keyword": "refund"}).json()
    assert [i["trace_id"] for i in r["items"]] == [BAD_ID]
    assert r["items"][0]["citations_valid"] is False


def test_unverified_excludes_refusals(client):
    r = client.get("/api/obs/traces", headers=admin(), params={"unverified": "true"}).json()
    assert [i["trace_id"] for i in r["items"]] == [BAD_ID]


def test_keyword_is_a_plain_substring_not_a_wildcard(client):
    assert client.get("/api/obs/traces", headers=admin(), params={"keyword": "%"}).json()["total"] == 0
    assert client.get("/api/obs/traces", headers=admin(), params={"keyword": "_"}).json()["total"] == 0


def test_filters_validate_input(client):
    assert client.get("/api/obs/traces", headers=admin(), params={"after": "not-a-date"}).status_code == 422
    assert client.get("/api/obs/traces", headers=admin(), params={"limit": 9999}).status_code == 422
    assert client.get("/api/obs/traces", headers=admin(), params={"prompt_version": "v2"}).json()["total"] == 2


def test_trace_detail_has_spans_and_context_ids(client):
    d = client.get(f"/api/obs/traces/{BAD_ID}", headers=admin()).json()
    assert [s["name"] for s in d["spans"]] == ["pre_retrieval_gate", "retrieval", "generation", "citation_validation"]
    assert d["retrieved_context_ids"] == ["A--b--c"]
    assert d["spans"][0]["logged"] is False
    assert client.get("/api/obs/traces/missing-id-1", headers=admin()).status_code == 404


def test_create_eval_case_from_trace(client):
    body = {"expected_behavior": "refusal", "mode": "corpus_gap", "notes": "from drill"}
    r = client.post(f"/api/obs/traces/{BAD_ID}/eval-case", headers=admin(), json=body)
    assert r.status_code == 201
    assert r.json()["case_id"] == "PF01" and r.json()["regression_trace_id"] == BAD_ID
    assert client.post(f"/api/obs/traces/{BAD_ID}/eval-case", headers=admin(), json=body).status_code == 409
    assert client.post(f"/api/obs/traces/{BAD_ID}/eval-case", headers=admin(),
                       json={"expected_behavior": "maybe"}).status_code == 422
    assert client.post("/api/obs/traces/nope-nope-1/eval-case", headers=admin(), json=body).status_code == 404
    assert client.get(f"/api/obs/traces/{BAD_ID}", headers=admin()).json()["eval_case_id"] == "PF01"


def test_stats_group_by_prompt_version(client):
    s = client.get("/api/obs/stats", headers=admin()).json()
    by = {v["prompt_version"]: v for v in s["by_prompt_version"]}
    assert set(by) == {"v1", "v2"}
    assert by["v1"]["unverified_answers"] == 1 and by["v2"]["unverified_answers"] == 0
    assert s["overall"]["avg_cost_usd"] == pytest.approx(0.0001)
    assert s["stages"][1]["stage"] == "generation"


def test_tenx_names_the_constraint_that_breaks_first(client, monkeypatch):
    monkeypatch.setenv("OBS_LIMIT_TPM", "8000")
    monkeypatch.setenv("OBS_LIMIT_RPD", "1000")
    t = client.get("/api/obs/tenx", headers=admin(), params={"baseline_rpm": 5, "multiplier": 10}).json()
    assert t["avg_tokens_per_request"] == 1000
    tpm = next(c for c in t["constraints"] if c["name"] == "tokens per minute")
    assert tpm["needed"] == 50000 and tpm["ratio"] == 6.25
    assert "tokens per minute" in t["verdict"]
    calm = client.get("/api/obs/tenx", headers=admin(), params={"baseline_rpm": 0.1, "multiplier": 1}).json()
    assert calm["verdict"].startswith("No configured rate limit")
    assert client.get("/api/obs/tenx", headers=admin(), params={"baseline_rpm": 0}).status_code == 422


def test_alert_config_never_leaks_secrets(client, monkeypatch):
    monkeypatch.setenv("ALERT_EMAIL_FROM", "alerts@example.com")
    monkeypatch.setenv("ALERT_EMAIL_TO", "team@example.com")
    monkeypatch.setenv("ALERT_EMAIL_PASSWORD", "super-secret-app-password")
    text = client.get("/api/obs/alerts/config", headers=admin()).text
    assert "super-secret-app-password" not in text and "alerts@example.com" not in text
    assert json.loads(text)["password_set"] is True


def test_alert_test_requires_settings(client):
    r = client.post("/api/obs/alerts/test", headers=admin())
    assert r.status_code == 400 and "ALERT_EMAIL_PASSWORD" in r.json()["detail"]


def test_alert_test_reports_smtp_failure_and_records_history(client, monkeypatch):
    monkeypatch.setenv("ALERT_EMAIL_FROM", "a@example.com")
    monkeypatch.setenv("ALERT_EMAIL_TO", "b@example.com")
    monkeypatch.setenv("ALERT_EMAIL_PASSWORD", "pw")

    def boom(subject, body, html=None):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(alerting, "send_alert_email", boom)
    monkeypatch.setattr("api.observability_router._last_test", {"at": 0.0})
    r = client.post("/api/obs/alerts/test", headers=admin()).json()
    assert r["ok"] is False and "smtp down" in r["message"]
    history = client.get("/api/obs/alerts", headers=admin()).json()
    assert history[0]["status"] == "failed" and history[0]["alert_type"] == "test"


def test_alert_conditions_and_rate_limit(client, monkeypatch):
    sent = []
    monkeypatch.setattr(alerting, "send_alert_email", lambda s, b, h=None: sent.append(s))
    monkeypatch.setattr(alerting, "_last_sent", {})
    record = _trace("t-x", "2026-10-12T10:00:00+00:00", answer=BAD, valid=False)
    types = [a[0] for a in alerting.evaluate_conditions(record)]
    assert "ungrounded_answer" in types and "blocklist_keyword" in types
    assert alerting.evaluate_conditions(_trace("t-r", "2026-10-12T10:00:00+00:00")) == []
    alerting._send_alerts(alerting.evaluate_conditions(record), record)
    alerting._send_alerts(alerting.evaluate_conditions(record), record)
    statuses = [a["status"] for a in client.get("/api/obs/alerts", headers=admin()).json()]
    assert len(sent) == 2 and statuses.count("sent") == 2 and statuses.count("suppressed") == 2


def test_drill_record_and_bar(client):
    ok = client.post("/api/obs/drills", headers=admin(), json={"trace_id": BAD_ID, "seconds": 42, "slice": "time"})
    assert ok.status_code == 201 and ok.json()["passed_bar"] is True
    slow = client.post("/api/obs/drills", headers=admin(), json={"trace_id": BAD_ID, "seconds": 301, "slice": "x"})
    assert slow.json()["passed_bar"] is False
    assert client.post("/api/obs/drills", headers=admin(), json={"trace_id": "nope", "seconds": 1, "slice": "x"}).status_code == 404
    assert client.post("/api/obs/drills", headers=admin(), json={"trace_id": BAD_ID, "seconds": -1, "slice": "x"}).status_code == 422
    assert len(client.get("/api/obs/drills", headers=admin()).json()) == 2


def _fake_pipeline(monkeypatch, answer):
    fake = SimpleNamespace(final_answer=answer, retrieved_chunks=[{"chunk_id": "A--b--c"}], trace_id="tr-1")
    monkeypatch.setattr("src.generation.answer.answer_question", lambda q: fake)


def test_run_case_red_then_green(client, monkeypatch):
    _fake_pipeline(monkeypatch, BAD)
    red = client.post("/api/obs/eval/cases/G01/run", headers=admin()).json()
    assert red["passed"] is False
    assert any(d["name"] == "refuses_corpus_gap" and not d["passed"] for d in red["detail"])
    _fake_pipeline(monkeypatch, REFUSAL)
    green = client.post("/api/obs/eval/cases/G01/run", headers=admin()).json()
    assert green["passed"] is True
    diff = client.get("/api/obs/eval/diff", headers=admin(), params={"base": red["run_id"], "head": green["run_id"]}).json()
    assert diff["summary"]["fixed"] == 1 and diff["summary"]["regressed"] == 0
    cases = client.get("/api/obs/eval/cases", headers=admin()).json()
    assert cases[0]["last_result"]["passed"] is True
    assert client.post("/api/obs/eval/cases/NOPE/run", headers=admin()).status_code == 404


def test_only_one_suite_at_a_time(client, monkeypatch):
    _fake_pipeline(monkeypatch, REFUSAL)
    monkeypatch.setattr(eval_runner.threading, "Thread", lambda **kw: SimpleNamespace(start=lambda: None))
    first = client.post("/api/obs/eval/runs", headers=admin())
    assert first.status_code == 202
    assert client.post("/api/obs/eval/runs", headers=admin()).status_code == 409
    assert client.post("/api/obs/eval/cases/G01/run", headers=admin()).status_code == 409


def test_suite_worker_records_pass_counts(client, monkeypatch):
    _fake_pipeline(monkeypatch, REFUSAL)
    eval_runner._claim_run("suite-t", "ui-suite", 1, "admin@example.com")
    eval_runner._suite_worker("suite-t", eval_runner.load_cases())
    run = client.get("/api/obs/eval/runs/suite-t", headers=admin()).json()
    assert run["run"]["status"] == "done" and run["run"]["passed"] == 1 and run["run"]["total"] == 1
    assert run["results"][0]["trace_id"] == "tr-1"


def test_demo_plant_is_disabled_by_default(client, fake, monkeypatch):
    assert client.post("/api/obs/demo/plant", headers=admin()).status_code == 404
    monkeypatch.setenv("OBS_DEMO_TOOLS", "true")
    r = client.post("/api/obs/demo/plant", headers=admin())
    assert r.status_code == 201
    planted = fake.created[-1]
    assert planted.kwargs["tags"][-1] == "demo-planted" and planted.kwargs["id"] == r.json()["trace_id"]
    assert planted.generations and planted.generations[0]["usage"]["totalCost"] > 0
    # not in the fake Langfuse yet (ingestion is asynchronous), but the drill still finds it straight away
    found = client.get("/api/obs/traces", headers=admin(), params={"keyword": "refund", "unverified": "true"}).json()
    assert r.json()["trace_id"] in [i["trace_id"] for i in found["items"]]


def test_alert_email_is_html_with_plain_text_fallback_and_escapes_content(monkeypatch):
    record = _trace("t-xss", "2026-10-12T10:00:00+00:00", question="<b>q</b>",
                    answer="<script>alert(1)</script> refund", valid=False)
    subject, text, html = email_template.render_alert("blocklist_keyword", "why <i>x</i>", record)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "&lt;b&gt;q&lt;/b&gt;" in html and "why &lt;i&gt;x&lt;/i&gt;" in html
    assert "t-xss" in subject or "t-xss"[:8] in subject
    assert "Open the trace: http" in text and "t-xss" in text
    assert "<html" in html.lower() and 'href="http' in html


def test_trace_link_uses_app_url_and_rejects_bad_schemes(monkeypatch):
    monkeypatch.setenv("ALERT_APP_URL", "https://support.example.com/")
    assert email_template.trace_link("a b") == "https://support.example.com/admin?tab=observability&trace=a%20b"
    assert email_template.trace_link(None) == "https://support.example.com/admin?tab=observability"
    monkeypatch.setenv("ALERT_APP_URL", "javascript:alert(1)")
    assert email_template.trace_link("x").startswith("http://localhost:4200/")


def test_send_alert_email_builds_multipart_message(monkeypatch):
    captured = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            captured["host"] = host

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            pass

        def login(self, user, password):
            captured["user"] = user

        def send_message(self, msg):
            captured["msg"] = msg

    monkeypatch.setattr(alerting.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("ALERT_EMAIL_FROM", "a@example.com")
    monkeypatch.setenv("ALERT_EMAIL_TO", "b@example.com")
    monkeypatch.setenv("ALERT_EMAIL_PASSWORD", "pw")
    subject, text, html = email_template.render_test("smtp.example.com")
    alerting.send_alert_email(subject, text, html)
    msg = captured["msg"]
    assert msg.get_content_type() == "multipart/alternative"
    assert [p.get_content_type() for p in msg.iter_parts()] == ["text/plain", "text/html"]
    assert msg["Subject"] == "[RAG Alert] Test alert"


# ------------------------------------------------------------------ user feedback

from src.observability import feedback as fb  # noqa: E402


class _Immediate:
    """Stand-in for threading.Thread that runs the target right away."""

    def __init__(self, target, args=(), daemon=None, **kwargs):
        self._target, self._args = target, args

    def start(self):
        self._target(*self._args)


@pytest.fixture
def fclient(client, monkeypatch):
    fb._recent.clear()
    calls = []
    monkeypatch.setattr(fb.threading, "Thread", _Immediate)
    monkeypatch.setattr(fb, "run_side_effects", lambda *args: calls.append(args))
    client.calls = calls
    return client


def member(email="alice@example.com"):
    return {"Authorization": "Bearer " + _make_jwt(email, "user")}


def vote(client, rating, reason=None, comment=None, trace=BAD_ID, headers=None):
    body = {"trace_id": trace, "rating": rating}
    if reason:
        body["reason_code"] = reason
    if comment:
        body["comment"] = comment
    return client.post("/api/feedback", json=body, headers=headers or member())


def test_feedback_requires_a_signed_in_user_but_not_admin(fclient):
    assert fclient.post("/api/feedback", json={"trace_id": BAD_ID, "rating": "up"}).status_code == 401
    assert vote(fclient, "up").status_code == 201


def test_thumbs_down_needs_a_valid_reason(fclient):
    assert vote(fclient, "down").status_code == 422
    assert vote(fclient, "down", reason="made_up").status_code == 422
    assert vote(fclient, "sideways").status_code == 422
    assert vote(fclient, "down", reason="wrong_answer", comment="x" * 1001).status_code == 422
    assert vote(fclient, "down", reason="wrong_answer", trace="nope").status_code == 404
    assert vote(fclient, "down", reason="wrong_answer").status_code == 201


def test_one_vote_per_user_and_email_only_for_a_new_thumbs_down(fclient):
    assert vote(fclient, "down", reason="wrong_answer", comment="no refunds exist").status_code == 201
    assert fclient.calls[-1][5] is True
    assert vote(fclient, "down", reason="incomplete").status_code == 201
    assert fclient.calls[-1][5] is False
    assert vote(fclient, "up").status_code == 201
    assert vote(fclient, "down", reason="wrong_answer").status_code == 201
    assert fclient.calls[-1][5] is True
    inbox = fclient.get("/api/obs/feedback", headers=admin()).json()
    assert inbox["total"] == 1 and inbox["items"][0]["rating"] == "down"
    # a user may only rate their own answers; someone else's trace looks the same as a missing one
    assert vote(fclient, "down", reason="wrong_answer", headers=member("bob@example.com")).status_code == 404
    assert vote(fclient, "down", reason="wrong_answer", trace=OK_ID, headers=member("bob@example.com")).status_code == 201
    assert fclient.get("/api/obs/feedback", headers=admin()).json()["total"] == 2


def test_feedback_rate_limit(fclient, monkeypatch):
    from src.catalog import settings
    settings.set("feedback.submit_limit", 2, "test")
    assert vote(fclient, "up").status_code == 201
    assert vote(fclient, "up").status_code == 201
    assert vote(fclient, "up").status_code == 429


def test_admin_inbox_filters_review_and_trace_detail(fclient):
    vote(fclient, "down", reason="wrong_answer", comment="there is no refund policy")
    vote(fclient, "up", trace=OK_ID, headers=member("bob@example.com"))
    assert fclient.get("/api/obs/feedback", headers=member()).status_code == 403
    down = fclient.get("/api/obs/feedback", headers=admin(), params={"rating": "down"}).json()
    item = down["items"][0]
    assert down["counts"]["new_down"] == 1 and item["reason_label"] == "The answer is wrong"
    assert item["question"] == "Can I get a refund?" and "refund" in item["answer_preview"]
    assert fclient.get("/api/obs/meta", headers=admin()).json()["feedback_new_down"] == 1
    detail = fclient.get(f"/api/obs/traces/{BAD_ID}", headers=admin()).json()
    assert detail["feedback"][0]["comment"] == "there is no refund policy"

    done = fclient.post(f"/api/obs/feedback/{item['id']}/review", headers=admin(),
                        json={"status": "reviewed", "admin_note": "added eval case"})
    assert done.status_code == 200
    reviewed = fclient.get("/api/obs/feedback", headers=admin(), params={"status": "reviewed"}).json()["items"][0]
    assert reviewed["reviewed_by"] == "admin@example.com" and reviewed["admin_note"] == "added eval case"
    assert fclient.get("/api/obs/meta", headers=admin()).json()["feedback_new_down"] == 0
    assert fclient.post("/api/obs/feedback/9999/review", headers=admin(), json={"status": "reviewed"}).status_code == 404
    assert fclient.post(f"/api/obs/feedback/{item['id']}/review", headers=admin(), json={"status": "bogus"}).status_code == 422


def _mail_env(monkeypatch, enabled="true"):
    monkeypatch.setenv("ALERT_EMAIL_ENABLED", enabled)
    monkeypatch.setenv("ALERT_EMAIL_FROM", "a@example.com")
    monkeypatch.setenv("ALERT_EMAIL_TO", "admin@example.com")
    monkeypatch.setenv("ALERT_EMAIL_PASSWORD", "pw")


def database_alerts():
    with database.get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM alerts ORDER BY id DESC")]


def test_thumbs_down_email_has_reason_user_trace_link_and_escapes_html(client, monkeypatch):
    _mail_env(monkeypatch)
    sent = []
    monkeypatch.setattr(alerting, "send_alert_email", lambda s, b, h=None: sent.append((s, b, h)))
    assert fb.email_admin("alice@example.com", BAD_ID, "wrong_answer", "<script>x</script> no refund policy",
                          trace_store.get_trace(BAD_ID)) is True
    subject, text, html = sent[0]
    assert "Thumbs down" in subject and "The answer is wrong" in subject
    assert "alice@example.com" in text and "tab=observability&trace=t-bad" in text
    assert "&lt;script&gt;" in html and "<script>" not in html
    assert "Review the trace" in html and "full refund" in html
    history = [a for a in database_alerts() if a["alert_type"] == "negative_feedback"]
    assert history[0]["status"] == "sent"


def test_thumbs_down_email_is_suppressed_or_fails_with_a_recorded_reason(client, monkeypatch):
    monkeypatch.setattr(alerting, "send_alert_email", lambda s, b, h=None: pytest.fail("must not send"))
    _mail_env(monkeypatch, enabled="false")
    assert fb.email_admin("a@example.com", BAD_ID, "wrong_answer", "") is False
    assert database_alerts()[0]["status"] == "suppressed"
    _mail_env(monkeypatch)
    monkeypatch.delenv("ALERT_EMAIL_PASSWORD")
    assert fb.email_admin("a@example.com", BAD_ID, "wrong_answer", "") is False
    assert database_alerts()[0]["status"] == "failed" and "ALERT_EMAIL_PASSWORD" in database_alerts()[0]["detail"]
    _mail_env(monkeypatch)
    monkeypatch.setenv("FEEDBACK_EMAIL_MAX_PER_HOUR", "0")
    assert fb.email_admin("a@example.com", BAD_ID, "wrong_answer", "") is False
    assert "cap" in database_alerts()[0]["detail"]


def test_smtp_failure_on_thumbs_down_is_recorded_not_raised(client, monkeypatch):
    _mail_env(monkeypatch)

    def boom(subject, body, html=None):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(alerting, "send_alert_email", boom)
    assert fb.email_admin("a@example.com", BAD_ID, "wrong_answer", "") is False
    assert "smtp down" in database_alerts()[0]["detail"]


def test_feedback_is_scored_on_the_langfuse_trace(monkeypatch):
    from src.generation import langfuse_client

    scores = []

    class FakeLangfuse:
        def score(self, **kwargs):
            scores.append(kwargs)

        def flush(self):
            pass

    monkeypatch.setattr(langfuse_client, "_langfuse", FakeLangfuse())
    assert fb.score_in_langfuse("alice@example.com", BAD_ID, "down", "wrong_answer", "no such policy") is True
    assert [s["name"] for s in scores] == ["user-feedback", "user-feedback-reason"]
    assert scores[0]["value"] == 0 and scores[0]["trace_id"] == BAD_ID and "no such policy" in scores[0]["comment"]
    assert scores[1]["value"] == "wrong_answer"
    key = fb.score_key(BAD_ID, "Alice@Example.com")
    assert key == fb.score_key(BAD_ID, "alice@example.com") and scores[0]["id"] == "fb-" + key
    scores.clear()
    fb.score_in_langfuse("alice@example.com", BAD_ID, "up", None, None)
    assert len(scores) == 1 and scores[0]["value"] == 1
    monkeypatch.setattr(langfuse_client, "_langfuse", None)
    assert fb.score_in_langfuse("a@example.com", BAD_ID, "up", None, None) is False


def test_trace_url_only_when_langfuse_is_configured(monkeypatch):
    from src.generation import langfuse_client

    monkeypatch.setattr(langfuse_client, "_langfuse", None)
    assert langfuse_client.trace_url("abc") is None
    monkeypatch.setattr(langfuse_client, "_langfuse", object())
    monkeypatch.setenv("LANGFUSE_HOST", "https://lf.example.com/")
    assert langfuse_client.trace_url("abc") == "https://lf.example.com/trace/abc"


# ------------------------------------------------------------------ Langfuse is the only trace store

def test_filters_langfuse_can_apply_are_sent_to_langfuse(client, fake):
    r = client.get("/api/obs/traces", headers=admin(), params={
        "after": f"{DAY}T00:00:00Z", "before": f"{DAY}T23:59:59Z", "prompt_version": "v1",
        "user": "alice@example.com"}).json()
    call = fake.fetch_calls[-1]
    assert call["name"] == "answer_question" and call["tags"] == ["prompt:v1"]
    assert call["user_id"] == "alice@example.com"
    assert call["from_timestamp"] is not None and call["to_timestamp"] is not None
    assert [i["trace_id"] for i in r["items"]] == [BAD_ID] and r["truncated"] is False


def test_keyword_cost_and_unverified_are_applied_after_fetching(client, fake):
    by_keyword = client.get("/api/obs/traces", headers=admin(), params={"keyword": "err-4032"}).json()
    assert [i["trace_id"] for i in by_keyword["items"]] == [OK_ID]
    assert by_keyword["scanned"] == 3
    assert client.get("/api/obs/traces", headers=admin(), params={"cost_above": 0.5}).json()["total"] == 0
    assert client.get("/api/obs/traces", headers=admin(), params={"user": "BOB@"}).json()["total"] == 1
    sent_user = [c["user_id"] for c in fake.fetch_calls]
    assert "BOB@" not in sent_user


def test_plain_browsing_uses_one_langfuse_call_per_page(client, fake):
    r = client.get("/api/obs/traces", headers=admin(), params={"limit": 2, "offset": 2}).json()
    assert len(fake.fetch_calls) == 1
    assert fake.fetch_calls[0]["page"] == 2 and fake.fetch_calls[0]["limit"] == 2
    assert r["total"] == 3 and len(r["items"]) == 1


def test_repeated_reads_are_cached_and_detail_needs_no_extra_call(client, fake):
    client.get("/api/obs/traces", headers=admin())
    client.get("/api/obs/traces", headers=admin())
    assert len(fake.fetch_calls) == 1
    detail = client.get(f"/api/obs/traces/{BAD_ID}", headers=admin())
    assert detail.status_code == 200 and fake.fetch_trace_calls == []


def test_unknown_trace_is_looked_up_once_in_langfuse(client, fake):
    assert client.get("/api/obs/traces/never-seen-123", headers=admin()).status_code == 404
    assert fake.fetch_trace_calls == ["never-seen-123"]


def test_not_configured_gives_a_clear_503(client, monkeypatch):
    monkeypatch.setattr(langfuse_client, "_langfuse", None)
    r = client.get("/api/obs/traces", headers=admin())
    assert r.status_code == 503 and "not configured" in r.json()["detail"]
    assert client.get("/api/obs/stats", headers=admin()).status_code == 503
    assert client.get("/api/obs/meta", headers=admin()).json()["langfuse_configured"] is False


def test_langfuse_rate_limit_is_explained(client, fake):
    fake.fail_with = FakeApiError(429, {"details": {"retryAfterSeconds": 56}})
    r = client.get("/api/obs/traces", headers=admin())
    assert r.status_code == 429 and "56 seconds" in r.json()["detail"]
    fake.fail_with = FakeApiError(500)
    trace_store.clear_cache()
    assert client.get("/api/obs/traces", headers=admin()).status_code == 502


def test_local_call_budget_protects_the_langfuse_quota(client, fake, monkeypatch):
    monkeypatch.setenv("LANGFUSE_API_MAX_PER_MIN", "2")
    trace_store.clear_cache()
    assert client.get("/api/obs/traces", headers=admin(), params={"prompt_version": "v1"}).status_code == 200
    assert client.get("/api/obs/traces", headers=admin(), params={"prompt_version": "v2"}).status_code == 200
    limited = client.get("/api/obs/traces", headers=admin(), params={"prompt_version": "v3"})
    assert limited.status_code == 429 and "Try again in" in limited.json()["detail"]
    assert len(fake.fetch_calls) == 2


def test_old_traces_without_the_full_snapshot_still_show(client, fake):
    old = _trace("t-old-0001", f"{DAY}T10:00:00+00:00", question="old question", answer="An old answer", valid=True)
    fake.add(old, old_style=True)
    trace_store.clear_cache()
    listed = client.get("/api/obs/traces", headers=admin(), params={"keyword": "old question"}).json()
    assert [i["trace_id"] for i in listed["items"]] == ["t-old-0001"]
    detail = client.get("/api/obs/traces/t-old-0001", headers=admin()).json()
    assert detail["context_recorded"] is False and detail["retrieved_context_ids"] == []
    assert detail["spans"][1]["logged"] is False and detail["unverified"] is False


def test_pipeline_writes_the_full_snapshot_to_langfuse_and_nothing_to_sqlite(client, fake, monkeypatch, tmp_path):
    from src.generation import answer as answer_module

    monkeypatch.setattr(answer_module, "_TRACES_PATH", tmp_path / "traces.jsonl")
    monkeypatch.delenv("TRACE_JSONL_MIRROR", raising=False)
    handle = fake.trace(id="shared-id-0001")
    ans = answer_module.Answer(
        question="q", retrieved_chunks=[{"chunk_id": "A--b--c", "article_id": "A", "score": 0.03, "rank": 1}],
        raw_answer="r", final_answer=BAD, citations=set(), citations_valid=False,
        retrieval_ms=40.0, generation_ms=900.0, input_tokens=800, output_tokens=60)
    answer_module._write_trace(ans, "q", 3, "col", "shared-id-0001", "carol@example.com", handle, fake, None)

    meta = handle.updates[-1]["metadata"]
    assert ans.trace_id == "shared-id-0001"
    assert meta["unverified"] is True and meta["retrieved_chunks"][0]["chunk_id"] == "A--b--c"
    assert meta["input_tokens"] == 800 and meta["cost_usd"] > 0 and meta["prompt_version"]
    assert handle.updates[-1]["output"]["final_answer"] == BAD
    with database.get_db() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "traces" not in tables
    assert not (tmp_path / "traces.jsonl").exists()
    # available immediately from memory, before Langfuse has ingested it
    assert trace_store.get_trace("shared-id-0001")["final_answer"] == BAD
    assert fake.fetch_trace_calls == []


def test_legacy_jsonl_mirror_is_opt_in(client, fake, monkeypatch, tmp_path):
    from src.generation import answer as answer_module

    mirror = tmp_path / "traces.jsonl"
    monkeypatch.setattr(answer_module, "_TRACES_PATH", mirror)
    monkeypatch.setenv("TRACE_JSONL_MIRROR", "true")
    ans = answer_module.Answer(question="q", retrieved_chunks=[], raw_answer="r", final_answer="r",
                               citations=set(), citations_valid=False)
    answer_module._write_trace(ans, "q", 3, "col", "mirror-id-0001", None, None, None, None)
    assert "mirror-id-0001" in mirror.read_text(encoding="utf-8")


def test_feedback_keeps_a_small_snapshot_so_the_inbox_needs_no_langfuse_call(fclient, fake):
    vote(fclient, "down", reason="wrong_answer", comment="no such policy")
    fake.fetch_calls.clear()
    item = fclient.get("/api/obs/feedback", headers=admin()).json()["items"][0]
    assert item["question"] == "Can I get a refund?" and "refund" in item["answer_preview"]
    assert item["prompt_version"] == "v1" and fake.fetch_calls == [] and fake.fetch_trace_calls == [BAD_ID]


def test_feedback_for_a_trace_that_langfuse_does_not_have_is_rejected(fclient, fake):
    assert vote(fclient, "up", trace="not-in-langfuse-1").status_code == 404
    fake.fail_with = FakeApiError(500)
    assert vote(fclient, "up", trace="another-trace-id-2").status_code == 503


def test_just_answered_trace_can_be_rated_without_a_langfuse_read(fclient, fake):
    record = _trace("fresh-trace-0001", YESTERDAY_TS, answer="Fresh answer [A--b--c]", valid=True)
    trace_store.remember(record)
    assert vote(fclient, "up", trace="fresh-trace-0001").status_code == 201
    assert fake.fetch_trace_calls == []


def test_stats_share_the_keyword_scan_and_flag_incomplete_windows(client, fake, monkeypatch):
    client.get("/api/obs/traces", headers=admin(), params={"keyword": "refund"})
    calls_after_search = len(fake.fetch_calls)
    stats = client.get("/api/obs/stats", headers=admin()).json()
    client.get("/api/obs/tenx", headers=admin())
    assert len(fake.fetch_calls) == calls_after_search
    assert stats["truncated"] is False and stats["scanned"] == 3
    monkeypatch.setenv("LANGFUSE_SCAN_LIMIT", "2")
    trace_store.clear_cache()
    short = client.get("/api/obs/stats", headers=admin()).json()
    assert short["scanned"] == 2 and short["truncated"] is True
    narrow = client.get("/api/obs/stats", headers=admin(), params={"days": 1}).json()
    assert narrow["truncated"] is False


def test_default_budget_matches_the_measured_langfuse_limit(monkeypatch):
    monkeypatch.delenv("LANGFUSE_API_MAX_PER_MIN", raising=False)
    monkeypatch.delenv("LANGFUSE_SCAN_LIMIT", raising=False)
    monkeypatch.delenv("LANGFUSE_CACHE_SECONDS", raising=False)
    assert trace_store.max_calls_per_minute() == 5
    assert trace_store.scan_limit() == 200 and trace_store.cache_seconds() == 60


def test_old_traces_with_tokens_but_no_cost_are_priced_from_their_tokens():
    old = SimpleNamespace(
        id="t-old-priced-1", timestamp=datetime.now(timezone.utc), name="answer_question", user_id=None, version=None,
        tags=[], input={"question": "q"}, output={"final_answer": "a [A--b--c]"}, latency=1.2, total_cost=0.0, scores=[],
        metadata={"model": "openai/gpt-oss-120b", "input_tokens": 1000, "output_tokens": 200, "citations_valid": True})
    item = trace_store.normalize(old)
    assert item["cost_usd"] == pytest.approx(0.00027, rel=0.01)
    assert item["prompt_version"] == "unknown" and item["generation_ms"] is None


def test_every_span_has_a_cost_and_totals_roll_up():
    from src.observability import tracing
    from tier1 import tracing_store
    rows = []
    tracing.set_sink(rows.append)
    try:
        with tracing.span("ticket", "request", trace_id="t-cost"):
            with tracing.span("tool:search", "tool"):
                pass
            with tracing.span("llm_call", "llm") as sp:
                sp.set(cost_usd=0.0004)
            with tracing.span("llm_call", "llm"):        # failed before usage came back: cost unknown
                pass
    finally:
        tracing.set_sink(None)
    by = {(r["name"], r["kind"]): r for r in rows}
    assert by[("tool:search", "tool")]["cost_usd"] == 0.0
    assert by[("ticket", "request")]["cost_usd"] == 0.0
    assert [r["cost_usd"] for r in rows if r["kind"] == "llm"] == [0.0004, None]
    for r in rows:
        r["attrs"] = r["attrs"] or {}
    assert tracing_store.tree(rows)[0]["cost_usd_total"] == pytest.approx(0.0004)

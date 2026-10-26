"""Production hardening: upload names, readiness detail, request ids, sessions for deleted users, login lockout,
stuck jobs after a restart, per-user rate limits."""
import io
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-32-chars-minimum!!")
os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")

from fastapi.testclient import TestClient

import api.main as main
from api import auth, database
from api.limiter import limiter
from auth_helpers import session_token

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def _temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()
    auth._failed.clear()


def _bearer(email, role="user"):
    return {"Authorization": "Bearer " + session_token(email, role)}


def test_upload_keeps_only_the_file_name_and_never_overwrites(tmp_path, monkeypatch):
    articles = tmp_path / "articles"
    monkeypatch.setattr(main, "_ARTICLES_DIR", articles)
    monkeypatch.setattr(main, "_allowed_upload_extensions", lambda: {".md"})
    import src.ingestion.ingest_document as ingest
    monkeypatch.setattr(ingest, "ingest_file", lambda path, collection: 3)
    admin = _bearer("admin@example.com", "admin")

    r = client.post("/api/upload", headers=admin,
                    files={"file": ("../../evil.md", io.BytesIO(b"# hi"), "text/markdown")})
    assert r.status_code == 200, r.text
    assert (articles / "evil.md").exists()
    assert not (tmp_path / "evil.md").exists() and not (tmp_path.parent / "evil.md").exists()

    again = client.post("/api/upload", headers=admin,
                        files={"file": ("evil.md", io.BytesIO(b"# other"), "text/markdown")})
    assert again.status_code == 409
    assert (articles / "evil.md").read_bytes() == b"# hi"


def test_ready_hides_problem_detail_from_anonymous_callers_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    body = client.get("/api/ready").json()
    assert set(body) == {"status"}
    detailed = client.get("/api/ready", headers=_bearer("admin@example.com", "admin")).json()
    assert "problems" in detailed and detailed["env"] == "production"


def test_every_response_has_a_request_id_and_a_sane_one_is_echoed():
    r = client.get("/api/health")
    assert len(r.headers["X-Request-ID"]) >= 8
    assert client.get("/api/health", headers={"X-Request-ID": "abc12345-xyz"}).headers["X-Request-ID"] == "abc12345-xyz"
    assert client.get("/api/health", headers={"X-Request-ID": "bad id\n"}).headers["X-Request-ID"] != "bad id\n"


def test_question_length_is_capped():
    r = client.post("/api/ask", json={"question": "x" * 2001}, headers=_bearer("user@example.com"))
    assert r.status_code == 422


def test_token_for_a_deleted_user_is_refused_even_if_it_claims_admin():
    headers = _bearer("gone@example.com", "admin")
    with database.get_db() as conn:
        conn.execute("DELETE FROM users WHERE email='gone@example.com'")
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_token_without_issuer_and_audience_is_refused():
    import jwt
    from api.config import JWT_ALGORITHM, JWT_SECRET
    session_token("user@example.com")
    bare = jwt.encode({"sub": "user@example.com", "role": "user", "exp": 9999999999}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + bare}).status_code == 401


def test_repeated_wrong_passwords_lock_that_email_for_a_while(monkeypatch):
    monkeypatch.setattr(auth, "PASSWORD_AUTH_ENABLED", True)
    pw = "correct-horse-battery"
    assert client.post("/api/auth/register", json={"email": "ann@example.com", "password": pw,
                                                   "full_name": "Ann"}).status_code == 201
    for _ in range(auth._FAILED_MAX):
        assert client.post("/api/auth/login", json={"email": "ann@example.com", "password": "wrong-one"}).status_code == 401
    locked = client.post("/api/auth/login", json={"email": "ANN@example.com", "password": pw})
    assert locked.status_code == 429


def test_jobs_left_running_by_a_restart_are_ended(tmp_path, monkeypatch):
    from tier1 import db as tier1_db, store
    monkeypatch.setattr(tier1_db, "DB_PATH", tmp_path / "t.db")
    tier1_db.init_db()
    job_id = store.create_job("user@example.com", "trace-123456")
    assert store.fail_interrupted_jobs() == 1
    job = store.get_job(job_id)
    assert job["status"] == "error" and "restart" in job["error"]


def test_answer_limit_is_per_user_not_per_address(monkeypatch):
    from starlette.requests import Request
    from api.limiter import user_or_ip
    token = session_token("user@example.com")

    def req(headers):
        scope = {"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
                 "client": ("10.0.0.1", 1234)}
        return Request(scope)

    assert user_or_ip(req({"Authorization": "Bearer " + token})) == "user:user@example.com"
    assert user_or_ip(req({"Authorization": "Bearer forged"})) == "ip:10.0.0.1"
    assert user_or_ip(req({})) == "ip:10.0.0.1"

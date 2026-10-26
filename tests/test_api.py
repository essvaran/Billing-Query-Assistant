"""Basic integration tests for the FastAPI routes."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Set required env vars before importing the app
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-32-chars-minimum!!")
os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _temp_db(tmp_path, monkeypatch):
    """Auth now reads the users table, so give each test a migrated throwaway database instead of data/app.db."""
    import api.database as database
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    database.init_db()


def _make_jwt(email: str, role: str = "user") -> str:
    from auth_helpers import session_token
    return session_token(email, role)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_unauthenticated():
    response = client.post("/api/ask", json={"question": "What is ERR-4032?"})
    assert response.status_code == 401


def test_ask_empty_question():
    token = _make_jwt("user@example.com")
    response = client.post(
        "/api/ask",
        json={"question": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_upload_requires_admin():
    user_token = _make_jwt("user@example.com", role="user")
    import io
    data = {"file": ("test.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    response = client.post(
        "/api/upload",
        files=data,
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert response.status_code == 403


def test_upload_rejects_bad_extension():
    admin_token = _make_jwt("admin@example.com", role="admin")
    import io
    data = {"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")}
    response = client.post(
        "/api/upload",
        files=data,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 400


def test_agent_run_unauthenticated():
    response = client.post("/api/agent/run", json={"ticket_id": "T001"})
    assert response.status_code == 401


def test_traces_unauthenticated():
    response = client.get("/api/traces")
    assert response.status_code == 401


def test_traces_are_admin_only():
    # the trace explorer shows other users' questions and its replay spends model quota
    token = _make_jwt("user@example.com")
    assert client.get("/api/traces", headers={"Authorization": f"Bearer {token}"}).status_code == 403
    for path in ("/api/agent/tickets", "/api/race/status", "/api/trajectory/status"):
        assert client.get(path, headers={"Authorization": f"Bearer {token}"}).status_code == 403, path


def test_traces_authenticated():
    token = _make_jwt("lead@example.com", role="admin")
    response = client.get(
        "/api/traces",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Returns 200 even with no traces file present
    assert response.status_code == 200
    body = response.json()
    assert "traces" in body
    assert "total" in body

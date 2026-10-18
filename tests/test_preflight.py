"""Startup checks: readable fixes for a stranger, hard stops only where production would be unsafe."""
import os

import pytest

os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("JWT_SECRET", "test-secret-for-preflight-tests-0123456789")
os.environ.setdefault("ADMIN_EMAIL", "lead@example.com")

from tier1 import preflight  # noqa: E402

GOOD = {"GROQ_API_KEY": "gsk_real_looking_key_123", "JWT_SECRET": "k9" * 20, "ADMIN_EMAIL": "lead@corp.test",
        "LLM_MODEL": "openai/gpt-oss-120b", "PII_HASH_SALT": "s3cr3t-salt-value"}


@pytest.fixture()
def env(monkeypatch):
    for k in ("APP_ENV", "LLM_CACHE", "TIER1_DEMO_CUSTOMER_ID", *GOOD):
        monkeypatch.delenv(k, raising=False)
    for k, v in GOOD.items():
        monkeypatch.setenv(k, v)
    return monkeypatch


def keys(problems, level=None):
    return {p.key for p in problems if level is None or p.level == level}


def test_a_complete_development_env_has_no_errors(env):
    assert keys(preflight.check_env(), "error") == set()


def test_placeholders_from_the_example_file_are_errors_with_a_fix(env):
    env.setenv("GROQ_API_KEY", "your_groq_api_key_here")
    env.setenv("JWT_SECRET", "change_me_to_a_random_secret")
    env.setenv("ADMIN_EMAIL", "your_admin_email@example.com")
    problems = preflight.check_env()
    assert keys(problems, "error") == {"GROQ_API_KEY", "JWT_SECRET", "ADMIN_EMAIL"}
    assert all(p.fix for p in problems)
    assert "gsk_" not in str([p.as_dict() for p in problems])      # never echoes a value


def test_short_secret_warns_in_development_and_stops_production(env):
    env.setenv("JWT_SECRET", "short-but-real")
    assert keys(preflight.check_env(), "warning") >= {"JWT_SECRET"}
    env.setenv("APP_ENV", "production")
    env.setenv("LLM_CACHE", "off")
    assert "JWT_SECRET" in keys(preflight.check_env(), "error")


def test_production_refuses_the_prompt_cache_the_demo_customer_and_the_example_salt(env):
    env.setenv("APP_ENV", "production")
    env.setenv("TIER1_DEMO_CUSTOMER_ID", "C1000")
    env.setenv("PII_HASH_SALT", "change-me")
    assert keys(preflight.check_env(), "error") == {"LLM_CACHE", "TIER1_DEMO_CUSTOMER_ID", "PII_HASH_SALT"}
    env.setenv("LLM_CACHE", "off")
    env.delenv("TIER1_DEMO_CUSTOMER_ID")
    env.setenv("PII_HASH_SALT", "private-salt")
    assert keys(preflight.check_env(), "error") == set()


def test_model_check_names_the_models_the_key_can_use(env):
    assert keys(preflight.check_models(None)) == {"provider"}
    assert keys(preflight.check_models([]), "error") == {"GROQ_API_KEY"}
    env.setenv("LLM_MODEL", "llama-3.3-70b-versatile")
    problems = preflight.check_models(["openai/gpt-oss-120b", "qwen/qwen3.8-27b"])
    assert keys(problems, "error") == {"LLM_MODEL"}
    assert "openai/gpt-oss-120b" in problems[0].fix


def test_ready_endpoint_reports_fixes_and_503_when_not_ready(env, tmp_path):
    from fastapi.testclient import TestClient
    from api.main import app
    env.setattr(preflight, "collection_size", lambda: 0)
    with TestClient(app) as client:
        r = client.get("/api/ready")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "not_ready" and "search_index" in {p["key"] for p in body["problems"]}
        env.setattr(preflight, "collection_size", lambda: 951)
        r = client.get("/api/ready")
        assert r.status_code == 200 and r.json()["status"] == "ready"
        assert client.get("/api/health").json() == {"status": "ok"}

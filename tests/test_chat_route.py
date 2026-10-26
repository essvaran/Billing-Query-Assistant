"""Chat front desk: which questions go to the Tier-1 assistant and which to Docs mode. The model is stubbed."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import chat_router, tier1_router
from api.auth import UserOut, get_current_user
from src.catalog import settings
from src.routing import route
from tier1 import db


def no_model(monkeypatch):
    """Fail the test if the classifier is called."""
    def boom(*_a, **_k):
        raise AssertionError("the model must not be called")
    monkeypatch.setattr("src.generation.llm_client.ask_llm", boom)


def model_says(monkeypatch, reply):
    calls = []

    def fake(system, user, *_a, **_k):
        calls.append(user)
        if isinstance(reply, Exception):
            raise reply
        return reply, 10, 3
    monkeypatch.setattr("src.generation.llm_client.ask_llm", fake)
    return calls


# --- decide_route ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["What does ERR-4032 mean?", "The migration is stuck with error 4032", "What causes PAY-1001?"])
def test_codes_documented_in_the_help_articles_go_to_docs(monkeypatch, text):
    no_model(monkeypatch)
    d = route.decide_route(text, has_account=True)
    assert (d.route, d.source) == ("docs", "code")


def test_codes_documented_in_the_store_help_centre_go_to_the_assistant(monkeypatch):
    no_model(monkeypatch)
    code = sorted(c for c in route._codes_in(route.VARIANT_A_CORPUS_DIR) if c.startswith("ERR-"))[0]
    d = route.decide_route(f"How do I download an invoice? I saw error {code}.", has_account=True)
    assert (d.route, d.source) == ("agent", "code")


def test_an_unknown_code_is_routed_by_its_family(monkeypatch):
    no_model(monkeypatch)
    d = route.decide_route("What does PLAN-ZZZ-V9 map to?", has_account=True)
    assert (d.route, d.source) == ("docs", "code")


@pytest.mark.parametrize("text", ["Where is my order O2017?", "I want my money back for order O2220.",
                                  "I think my account was hacked.", "I was charged twice this month"])
def test_account_questions_go_to_the_assistant_by_rule(monkeypatch, text):
    no_model(monkeypatch)
    d = route.decide_route(text, has_account=True)
    assert (d.route, d.source) == ("agent", "rule")


@pytest.mark.parametrize("text", ["How long does a billing migration typically take?",
                                  "What happens to auto-pay during a billing migration?",
                                  "Can a completed billing migration be rolled back?"])
def test_general_billing_questions_go_to_docs_by_rule(monkeypatch, text):
    no_model(monkeypatch)
    d = route.decide_route(text, has_account=True)
    assert (d.route, d.source) == ("docs", "rule")


def test_both_lists_matching_asks_the_model(monkeypatch):
    calls = model_says(monkeypatch, '{"route": "docs"}')
    d = route.decide_route("Can I get a refund if my billing migration fails?", has_account=True)
    assert (d.route, d.source) == ("docs", "llm") and len(calls) == 1


def test_no_list_matching_asks_the_model(monkeypatch):
    model_says(monkeypatch, 'Sure. {"route": "agent"}')
    d = route.decide_route("Is there a phone number I can call?", has_account=True)
    assert (d.route, d.source) == ("agent", "llm")


@pytest.mark.parametrize("reply", [RuntimeError("down"), "no json here", '{"route": "billing"}'])
def test_model_failure_falls_back_on_the_account(monkeypatch, reply):
    model_says(monkeypatch, reply)
    assert route.decide_route("Is there a phone number I can call?", has_account=True).as_dict() == \
        {"route": "agent", "source": "fallback", "reason": "no clear signal", "needs_account": False}
    assert route.decide_route("Is there a phone number I can call?", has_account=False).route == "docs"


def test_model_step_can_be_switched_off(monkeypatch):
    no_model(monkeypatch)
    settings.set("routing.use_llm", False, "test")
    assert route.decide_route("Is there a phone number I can call?", has_account=True).source == "fallback"


def test_assistant_route_without_an_account_goes_to_docs_and_says_why(monkeypatch):
    no_model(monkeypatch)
    d = route.decide_route("Where is my order O2017?", has_account=False)
    assert (d.route, d.needs_account) == ("docs", True)


# --- POST /api/chat/route -------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(tier1_router.tracing_store, "install", lambda: None)
    monkeypatch.setattr(chat_router, "get_langfuse", lambda: None)
    app = FastAPI()
    app.include_router(chat_router.router)
    c = TestClient(app)
    c.app_ref = app
    return c


def act_as(client, email, role):
    client.app_ref.dependency_overrides[get_current_user] = lambda: UserOut(email=email, role=role)


def test_endpoint_needs_a_sign_in(client):
    assert client.post("/api/chat/route", json={"text": "hi"}).status_code == 401


def test_endpoint_rejects_empty_and_oversized_questions(client):
    act_as(client, "lead@example.com", "admin")
    assert client.post("/api/chat/route", json={"text": "   "}).status_code == 400
    assert client.post("/api/chat/route", json={"text": "x" * 4001}).status_code == 422


def test_admin_has_an_account_only_with_a_real_customer_chosen(client, monkeypatch):
    no_model(monkeypatch)
    act_as(client, "lead@example.com", "admin")
    q = {"text": "Where is my order O2017?"}
    assert client.post("/api/chat/route", json={**q, "customer_id": "C1000"}).json() == \
        {"route": "agent", "source": "rule", "reason": "matched \\bO\\d{4}\\b", "needs_account": False}
    assert client.post("/api/chat/route", json=q).json()["needs_account"] is True
    assert client.post("/api/chat/route", json={**q, "customer_id": "NOPE"}).json()["needs_account"] is True


def test_user_without_a_linked_customer_is_sent_to_docs(client, monkeypatch):
    no_model(monkeypatch)
    act_as(client, "user@example.com", "user")
    body = client.post("/api/chat/route", json={"text": "Where is my order O2017?"}).json()
    assert (body["route"], body["needs_account"]) == ("docs", True)

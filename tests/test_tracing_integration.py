"""One trace id across the API, the agent loop and both MCP servers, and no PII in any sink.

The LLM is scripted (no network, no quota); the agent loop, the MCP client, both MCP server
processes, the guards and the span store are all real.
"""
import json
from pathlib import Path

import pytest

from agent import agent_loop
from src.generation import gateway, langfuse_client
from src.observability import redact
from tier1 import db, tracing_store
from tier1.models import TicketRequest

ROOT = Path(__file__).resolve().parent.parent


def _index_ready() -> bool:
    try:
        from src.config import TIER1_COLLECTION
        from src.retrieval.vector_store import get_collection
        return get_collection(TIER1_COLLECTION).count() > 0
    except Exception:
        return False


# These tests start the real help-centre MCP server, which needs the embedding model and the built index.
pytestmark = pytest.mark.skipif(not _index_ready(), reason="run `make ingest` first (needs the embedding model)")


def _tool_call(call_id, name, args):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def _resp(message, finish="tool_calls"):
    return {"choices": [{"finish_reason": finish, "message": message}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            "gateway": {"cache": "miss", "waited_s": 0.0, "attempts": 1}}


class FakeLangfuse:
    """Captures everything that would be sent to Langfuse."""
    def __init__(self):
        self.sent = []
        self.id = "lf-1"

    def trace(self, **kw):
        self.sent.append(kw)
        return self

    def span(self, **kw):
        self.sent.append(kw)
        return self

    def generation(self, **kw):
        self.sent.append(kw)
        return self

    def update(self, **kw):
        self.sent.append(kw)

    def end(self, **kw):
        self.sent.append(kw)

    def flush(self):
        pass


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)                                  # the service resolves mcp_config.tier1.json from here
    monkeypatch.setenv("TIER1_DB_PATH", str(tmp_path / "t.db"))  # forwarded to the MCP server processes
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.delenv("TIER1_AS_OF", raising=False)
    # These tests script the model making every call itself; the prefetch path has its own test below.
    monkeypatch.setenv("TIER1_ABLATE", "prefetch")
    db.seed_from_synthetic()
    agent_loop._mcps.clear()                                 # no manager connected under another database
    fake = FakeLangfuse()
    monkeypatch.setattr(langfuse_client, "_langfuse", redact.RedactingProxy(fake))
    yield fake
    agent_loop._mcps.clear()
    redact.set_known_pii_provider(None)


def _customer_with_order(version):
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT c.*, o.order_id FROM customers c JOIN orders o USING(customer_id) "
            "WHERE c.policy_version=? LIMIT 1", (version,)).fetchone()
    return dict(row)


def _script(monkeypatch, steps):
    """steps: list of callables(messages) -> message dict. Returns the call counter."""
    state = {"n": 0}

    def fake_chat(messages, tools=None, model=None, **kw):
        step = steps[min(state["n"], len(steps) - 1)]
        state["n"] += 1
        msg = step(messages)
        return _resp(msg, "tool_calls" if msg.get("tool_calls") else "stop")

    monkeypatch.setattr(gateway, "chat", fake_chat)
    return state


def _all_text_from_db():
    with db.get_conn() as conn:
        spans = [dict(r) for r in conn.execute("SELECT * FROM spans")]
        handoffs = [dict(r) for r in conn.execute("SELECT * FROM handoffs")]
    return json.dumps(spans) + json.dumps(handoffs)


def test_one_trace_id_across_every_hop_with_cost_and_latency(env, monkeypatch, capfd):
    from tier1.service import handle_ticket

    cust = _customer_with_order("refund-30d")
    body = (f"I want a refund for order {cust['order_id']}. My email is {cust['email']} and I live at "
            f"{cust['address']}. Regards, {cust['name']}")

    def lap1(_m):
        return {"role": "assistant", "content": None, "tool_calls": [
            _tool_call("c1", "check_entitlement", {"customer_id": cust["customer_id"], "order_id": cust["order_id"]})]}

    def lap2(_m):
        return {"role": "assistant", "content": None, "tool_calls": [
            _tool_call("c2", "search_help_centre", {"query": "refund window days", "policy_version": "refund-30d"})]}

    def lap3(messages):
        found = json.loads([m for m in messages if m["role"] == "tool"][-1]["content"])
        chunk_id = found["results"][0]["chunk_id"]
        return {"role": "assistant", "content":
                f"Your account is on the 30-day refund policy and the order is within it [{chunk_id}]. "
                "A support agent will confirm."}

    _script(monkeypatch, [lap1, lap2, lap3])
    resp = handle_ticket(TicketRequest(body=body, subject="Refund", customer_id=cust["customer_id"],
                                       order_id=cust["order_id"], ticket_id="TK-TEST"))
    assert resp.decision == "ANSWER", (resp.reason, resp.violations)

    spans = tracing_store.get_spans(resp.trace_id)
    kinds = {s["kind"] for s in spans}
    assert {"request", "guard", "llm", "tool", "mcp_server", "retrieval"} <= kinds
    assert {s["trace_id"] for s in spans} == {resp.trace_id}

    # the server-side span hangs under the client's tool span: the id crossed the stdio hop
    by_name = {s["name"]: s for s in spans}
    assert by_name["server:check_entitlement"]["parent_id"] == by_name["tool:check_entitlement"]["span_id"]
    assert by_name["server:search_help_centre"]["parent_id"] == by_name["tool:search_help_centre"]["span_id"]
    assert by_name["retrieval"]["parent_id"] == by_name["server:search_help_centre"]["span_id"]

    summary = tracing_store.summarize(spans)
    assert summary["llm_calls"] == 3 and summary["cost_usd"] > 0 and summary["total_ms"] > 0
    assert all(s["duration_ms"] >= 0 for s in spans)
    assert sorted(summary["mcp_servers_seen"]) == ["help-centre", "tier1-tools"]
    assert resp.cost_usd == pytest.approx(summary["cost_usd"], abs=1e-6)

    # --- the PII line: the ticket carried a real email, address and name; no sink may keep them ---
    secrets = [cust["email"], cust["address"], cust["name"], cust["customer_id"], cust["order_id"]]
    sinks = {
        "spans+handoffs": _all_text_from_db(),
        "langfuse": json.dumps(env.sent, default=str),
        "server stderr": capfd.readouterr().err,
    }
    assert env.sent, "the fake Langfuse should have received traffic"
    for sink, text in sinks.items():
        for secret in secrets:
            assert secret not in text, f"{secret!r} leaked into {sink}"


def test_wire_log_and_handoff_summary_are_scrubbed(env, monkeypatch, tmp_path):
    from tier1.service import handle_ticket

    cust = _customer_with_order("refund-14d")
    leak = f"customer {cust['name']} at {cust['address']} ({cust['email']})"

    def lap1(_m):
        return {"role": "assistant", "content": None, "tool_calls": [
            _tool_call("c1", "escalate", {"ticket_ref": "TK-9", "reason": "not_tier1", "summary": leak})]}

    _script(monkeypatch, [lap1])
    resp = handle_ticket(TicketRequest(body="Can you recommend another company?", subject="Hi",
                                       customer_id=cust["customer_id"], ticket_id="TK-9"))
    assert resp.decision == "ESCALATE" and resp.handoff_id

    text = _all_text_from_db()
    for secret in (cust["email"], cust["address"], cust["name"]):
        assert secret not in text

    wire = tmp_path / "wire.json"
    agent_loop._mcps["mcp_config.tier1.json"].save_wire_log(str(wire))
    for secret in (cust["email"], cust["address"], cust["customer_id"]):
        assert secret not in wire.read_text(encoding="utf-8")


def test_prefetch_makes_the_two_calls_in_code_and_the_model_answers_in_one_lap(env, monkeypatch):
    from tier1.service import handle_ticket

    monkeypatch.delenv("TIER1_ABLATE", raising=False)
    cust = _customer_with_order("refund-30d")
    seen = {}

    def lap1(messages):
        tool_msgs = [m for m in messages if m["role"] == "tool"]
        seen["tool_msgs"] = len(tool_msgs)
        found = json.loads(tool_msgs[-1]["content"])
        return {"role": "assistant", "content":
                f"Your account is on the 30-day refund policy [{found['results'][0]['chunk_id']}]. A support agent will confirm."}

    state = _script(monkeypatch, [lap1])
    resp = handle_ticket(TicketRequest(body=f"I want a refund for order {cust['order_id']}.", subject="Refund",
                                       customer_id=cust["customer_id"], order_id=cust["order_id"], ticket_id="TK-PF"))
    assert resp.decision == "ANSWER", (resp.reason, resp.violations)
    assert state["n"] == 1 and resp.laps == 1
    assert seen["tool_msgs"] == 2                       # both results were in front of the model on lap 1
    assert resp.tools_called == ["check_entitlement", "search_help_centre"]
    assert resp.model_tools_called == []                # the model is not credited with calls code made

    spans = tracing_store.get_spans(resp.trace_id)
    by_name = {s["name"]: s for s in spans}
    # the prefetched calls cross the MCP hop exactly like model calls: same trace, parent ids preserved
    assert by_name["server:check_entitlement"]["parent_id"] == by_name["tool:check_entitlement"]["span_id"]
    assert by_name["server:search_help_centre"]["parent_id"] == by_name["tool:search_help_centre"]["span_id"]
    search_args = json.loads(by_name["tool:search_help_centre"]["attrs"]) if isinstance(by_name["tool:search_help_centre"]["attrs"], str) else by_name["tool:search_help_centre"]["attrs"]
    assert search_args.get("origin") == "code"


def test_search_query_puts_error_codes_first():
    from tier1.service import _search_query

    q = _search_query("Checkout fails", "I keep getting ERR-4040 when I pay. ERR-4040 again!")
    assert q.startswith("ERR-4040 ")
    assert q.count("ERR-4040") == 3                     # once up front, then the customer's own words
    assert len(_search_query("x", "y" * 1000)) <= 300

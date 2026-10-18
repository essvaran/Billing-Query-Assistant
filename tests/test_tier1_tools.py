"""Tier-1 tools and the MCP client behaviours added in Week 12 (requirements 2 and 3)."""
import json
import sys

import pytest

from tier1 import db, tools


@pytest.fixture()
def tier1_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tier1.db")
    monkeypatch.delenv("TIER1_AS_OF", raising=False)
    db.seed_from_synthetic()
    return db


def _customer(version):
    with db.get_conn() as conn:
        return dict(conn.execute("SELECT * FROM customers WHERE policy_version=? LIMIT 1", (version,)).fetchone())


def _order_aged(customer_id, days):
    """An order of this customer whose age is `days`, or None."""
    with db.get_conn() as conn:
        for row in conn.execute("SELECT * FROM orders WHERE customer_id=?", (customer_id,)):
            if (db.as_of() - __import__("datetime").date.fromisoformat(row["purchase_date"])).days == days:
                return dict(row)
    return None


def test_seed_is_idempotent(tier1_db):
    assert tier1_db.seed_from_synthetic() == {"seeded": False}


def test_entitlement_returns_the_customers_policy_version(tier1_db):
    for version, days in (("refund-14d", 14), ("refund-30d", 30)):
        c = _customer(version)
        out = tools.check_entitlement(c["customer_id"])
        assert out["policy_version"] == version and out["refund_days"] == days


def test_unknown_customer_is_an_error_not_a_guess(tier1_db):
    assert tools.check_entitlement("C9999")["error"] == "not_found"


def test_no_customer_pii_leaves_the_tools(tier1_db):
    c = _customer("refund-30d")
    with db.get_conn() as conn:
        o = dict(conn.execute("SELECT * FROM orders WHERE customer_id=? LIMIT 1", (c["customer_id"],)).fetchone())
    blob = json.dumps(tools.check_entitlement(c["customer_id"], o["order_id"])) + json.dumps(tools.lookup_order(o["order_id"]))
    assert c["email"] not in blob and c["address"] not in blob and c["name"] not in blob


def test_refund_eligibility_is_computed_in_code_at_the_boundary(tier1_db):
    with db.get_conn() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT o.order_id, o.customer_id, o.purchase_date, c.refund_days FROM orders o "
            "JOIN customers c USING(customer_id)")]
    checked = 0
    for r in rows:
        age = (db.as_of() - __import__("datetime").date.fromisoformat(r["purchase_date"])).days
        if age in (r["refund_days"], r["refund_days"] + 1):
            out = tools.check_entitlement(r["customer_id"], r["order_id"])["refund_check"]
            assert out["eligible"] == (age <= r["refund_days"]), (age, r["refund_days"])
            checked += 1
    assert checked > 0, "synthetic data should contain boundary cases"


def test_order_of_another_customer_is_refused(tier1_db):
    with db.get_conn() as conn:
        o = dict(conn.execute("SELECT * FROM orders LIMIT 1").fetchone())
        other = conn.execute("SELECT customer_id FROM customers WHERE customer_id<>?", (o["customer_id"],)).fetchone()[0]
    out = tools.check_entitlement(other, o["order_id"])
    assert out["refund_check"]["error"] == "order_belongs_to_another_customer"


def test_escalate_stores_a_handoff_and_normalises_unknown_reason(tier1_db):
    res = tools.escalate("TK1", "made_up_reason", "customer threatens legal action", trace_id="t-1")
    assert res["status"] == "queued"
    row = db.list_handoffs()[0]
    assert row["reason"] == "other" and row["trace_id"] == "t-1" and row["ticket_ref"] == "TK1"


# --- MCP client: discovery, allow-list, hidden trace id (real stdio servers) ---------------

def _config(tmp_path, allowed):
    from pathlib import Path
    script = str(Path(__file__).resolve().parent.parent / "mcp_servers" / "tier1_tools_server.py")
    cfg = {"mcpServers": {"tier1-tools": {
        "command": "python", "args": [script], "allowed_tools": allowed}}}
    path = tmp_path / "mcp_config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


@pytest.fixture()
def mcp_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TIER1_DB_PATH", str(tmp_path / "mcp.db"))
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "mcp.db")
    return tmp_path


def _connect(path):
    from agent.mcp_client import MCPManager
    mgr = MCPManager(str(path), connect_timeout=60)
    mgr.connect()
    return mgr


def test_allow_list_hides_tools_and_trace_id_is_not_in_the_model_schema(mcp_env):
    import agent.mcp_client as mc
    cfg = _config(mcp_env, ["lookup_order", "escalate"])
    mgr = _connect(cfg)
    assert sorted(mgr.get_tool_names()) == ["escalate", "lookup_order"]
    assert mgr.blocked_tools() == ["tier1-tools.check_entitlement"]
    for s in mgr.get_tool_schemas():
        assert "trace_id" not in s["function"]["parameters"].get("properties", {})
        assert "trace_id" not in s["function"]["parameters"].get("required", [])
    assert mc.TRACE_ARG == "trace_id"


def test_client_injects_its_trace_id_and_ignores_the_models(mcp_env):
    cfg = _config(mcp_env, ["escalate"])
    mgr = _connect(cfg)
    args = json.dumps({"ticket_ref": "TK9", "reason": "not_tier1", "summary": "x", "trace_id": "model-made-this-up"})
    out = json.loads(mgr.dispatch_tool("escalate", args, trace_id="request-123"))
    assert out["status"] == "queued"
    assert db.list_handoffs()[0]["trace_id"] == "request-123"

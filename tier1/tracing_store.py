"""SQLite sink and queries for spans (the `spans` table in data/tier1.db).

install() is called once per process: by the service, and by each MCP server at startup. Because
every process writes to the same WAL-mode SQLite file, one query returns the whole tree for a
trace id, across the API, the agent and both MCP servers.
"""
import json
import time

from src.observability import redact, tracing
from tier1 import db

_PII_TTL_S = 60.0
_pii_cache: tuple[float, list[str]] = (0.0, [])


def _known_pii() -> list[str]:
    """Names, emails and addresses of all customers, for exact-match scrubbing. Cached."""
    global _pii_cache
    now = time.monotonic()
    if now - _pii_cache[0] > _PII_TTL_S:
        try:
            with db.get_conn() as conn:
                rows = conn.execute("SELECT name, email, address FROM customers").fetchall()
            _pii_cache = (now, [v for r in rows for v in (r["name"], r["email"], r["address"]) if v])
        except Exception:
            _pii_cache = (now, _pii_cache[1])
    return _pii_cache[1]


def write_span(row: dict) -> None:
    with db.get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO spans (span_id, trace_id, parent_id, name, kind, started_at, duration_ms, "
            "input_tokens, output_tokens, cost_usd, status, attrs) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (row["span_id"], row["trace_id"], row["parent_id"], row["name"], row["kind"], row["started_at"],
             row["duration_ms"], row["input_tokens"], row["output_tokens"], row["cost_usd"], row["status"],
             json.dumps(row["attrs"], default=str)),
        )


def install() -> None:
    db.init_db()
    redact.set_known_pii_provider(_known_pii)
    tracing.set_sink(write_span)


def get_spans(trace_id: str) -> list[dict]:
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM spans WHERE trace_id=? ORDER BY started_at, rowid", (trace_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["attrs"] = json.loads(d["attrs"] or "{}")
        d["cost_usd"] = tracing.own_cost(d["kind"], d["cost_usd"])     # spans stored before every span had a cost
        out.append(d)
    return out


def summarize(spans: list[dict]) -> dict:
    """Totals for one trace: cost, tokens, time split between model, tools and queueing."""
    llm = [s for s in spans if s["kind"] == "llm"]
    tools = [s for s in spans if s["kind"] == "tool"]
    servers = [s for s in spans if s["kind"] == "mcp_server"]
    roots = [s for s in spans if s["parent_id"] is None]
    return {
        "trace_id": spans[0]["trace_id"] if spans else None,
        "spans": len(spans),
        "total_ms": max((s["duration_ms"] for s in roots), default=0.0),
        "cost_usd": round(sum(s["cost_usd"] or 0 for s in spans), 8),
        "input_tokens": sum(s["input_tokens"] or 0 for s in spans),
        "output_tokens": sum(s["output_tokens"] or 0 for s in spans),
        "llm_calls": len(llm),
        "llm_ms": round(sum(s["duration_ms"] for s in llm), 1),
        "queue_wait_s": round(sum(s["attrs"].get("waited_s", 0) or 0 for s in llm), 2),
        "tool_calls": len(tools),
        "tool_ms": round(sum(s["duration_ms"] for s in tools), 1),
        "mcp_server_spans": len(servers),
        "mcp_servers_seen": sorted({s["attrs"].get("server", s["name"]) for s in servers}),
        "errors": [s["name"] for s in spans if s["status"] != "ok"],
    }


def tree(spans: list[dict]) -> list[dict]:
    """Nest spans under their parents. Orphans (parent not recorded) are returned as roots."""
    by_id = {s["span_id"]: {**s, "children": []} for s in spans}
    roots = []
    for s in spans:
        node = by_id[s["span_id"]]
        parent = by_id.get(s["parent_id"]) if s["parent_id"] else None
        (parent["children"] if parent else roots).append(node)
    for root in roots:
        _roll_up(root)
    return roots


def _roll_up(node: dict) -> float:
    """cost_usd_total: the span's own cost plus everything under it (the root's total is the ticket's cost)."""
    node["cost_usd_total"] = round((node["cost_usd"] or 0) + sum(_roll_up(c) for c in node["children"]), 8)
    return node["cost_usd_total"]

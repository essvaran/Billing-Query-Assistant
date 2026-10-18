"""MCP server: Tier-1 account tools (lookup_order, check_entitlement, escalate).

Every tool takes optional `trace_id` and `parent_span_id`. The MCP client injects them on each call
and hides them from the model's tool schema, so the id of the originating ticket and the client's
tool span survive the stdio hop (stdio has no headers to carry them). The server records its own span
under that parent and logs the trace id to stderr; stdout belongs to the MCP protocol.
"""
import json
import sys
import time
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from mcp.server.fastmcp import FastMCP as MCPServer

from src.observability import tracing
from tier1 import db, tools, tracing_store

mcp = MCPServer("tier1-tools")
db.seed_from_synthetic()  # no-op when already seeded
tracing_store.install()


def _run(tool: str, fn, trace_id: str, parent_span_id: str, **kwargs) -> str:
    started = time.perf_counter()
    ok = False
    with tracing.span(f"server:{tool}", "mcp_server", trace_id=trace_id or None,
                      parent_id=parent_span_id or None, server="tier1-tools", tool=tool) as sp:
        try:
            result = fn(**kwargs)
            ok = "error" not in result
            sp.set(ok=ok, status="ok" if ok else "error")
            payload = json.dumps(result)
        except Exception as exc:  # a tool failure must reach the agent as data, not crash the server
            sp.set(ok=False, status="error", error=type(exc).__name__)
            payload = json.dumps({"error": "tool_failure", "detail": type(exc).__name__})
    print(
        f"[tier1-tools] trace_id={trace_id or '-'} tool={tool} ok={ok} "
        f"ms={(time.perf_counter() - started) * 1000:.1f}",
        file=sys.stderr,
        flush=True,
    )
    return payload


@mcp.tool()
def lookup_order(order_id: str, trace_id: str = "", parent_span_id: str = "") -> str:
    """Look up an order by order_id (format O2000). Returns purchase date, days since
    purchase, amount, currency and status. Returns not_found if the order does not
    exist; never guess an order id."""
    return _run("lookup_order", tools.lookup_order, trace_id, parent_span_id, order_id=order_id)


@mcp.tool()
def check_entitlement(customer_id: str, order_id: str = "", trace_id: str = "", parent_span_id: str = "") -> str:
    """Check what a customer is entitled to. MUST be called before saying anything
    about refunds or shipping. Returns the plan, the refund-policy version that
    applies to this customer (refund-14d or refund-30d), the refund window in days,
    the shipping SLA, and, when order_id is given, whether the order is eligible
    for a refund (computed by the system, not by you)."""
    return _run("check_entitlement", tools.check_entitlement, trace_id, parent_span_id,
                customer_id=customer_id, order_id=order_id)


def escalate(ticket_ref: str, reason: str, summary: str, trace_id: str = "", parent_span_id: str = "") -> str:
    return _run("escalate", lambda **kw: tools.escalate(trace_id=trace_id, **kw), trace_id, parent_span_id,
                ticket_ref=ticket_ref, reason=reason, summary=summary)


def _escalate_description() -> str:
    """The reason list a model may use is the active catalog list escalation_reason (read when the server starts)."""
    from src.catalog import ref
    machine = {"budget_exceeded", "tool_error", "rate_limited"}          # set by code, never chosen by the model
    reasons = ", ".join(c for c in ref.codes("escalation_reason") if c not in machine)
    return ("Hand the ticket to a human agent. Use when the ticket is not a Tier-1 question, mentions legal action, safety, "
            "fraud or a chargeback, when information needed to answer cannot be found, or when you are not sure. "
            f"reason must be one of: {reasons}. summary: what the customer asked and what you already checked, "
            "so the human does not repeat the work.")


escalate.__doc__ = _escalate_description()
escalate = mcp.tool()(escalate)


if __name__ == "__main__":
    mcp.run(transport="stdio")

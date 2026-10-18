"""MCP server exposing ticket lifecycle and escalation history.

Two tools:
  - lookup_ticket_history: status changes, assignments, timeline
  - get_escalation_history: escalation chain with reasons and timestamps
"""

import json
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ticket-history")

# Synthetic history data keyed by ticket_id
def _row(ticket_id: str):
    """History and escalation chain from data/app.db (table ticket_histories)."""
    from api.database import get_db, init_db
    init_db()
    with get_db() as conn:
        r = conn.execute("SELECT history, escalations FROM ticket_histories WHERE ticket_id=?", (ticket_id,)).fetchone()
    return (json.loads(r["history"]) if r and r["history"] else None, json.loads(r["escalations"]) if r else [])


@mcp.tool()
def lookup_ticket_history(ticket_id: str) -> str:
    """Look up the full lifecycle history of a support ticket by ticket_id
    (format: Tnnn, e.g. T002, T008).

    Returns the creation timestamp, status change timeline, and
    list of assigned agents. If the ticket has no recorded history,
    returns a clear message so you can tell the user rather than
    retrying the same call.
    """
    record, _ = _row(ticket_id)
    if record is None:
        return json.dumps({
            "error": "not_found",
            "ticket_id": ticket_id,
            "hint": f"No history for {ticket_id} -- ticket IDs look like Tnnn (e.g. T002, T008).",
        })
    return json.dumps(record)


@mcp.tool()
def get_escalation_history(ticket_id: str) -> str:
    """Get the escalation chain for a support ticket by ticket_id
    (format: Tnnn, e.g. T003, T008).

    Returns a list of escalation events with timestamps, the agents
    involved, the reason for escalation, and the escalation level.
    If no escalations exist for this ticket, returns an empty list
    with a note that the ticket was never escalated.
    """
    _, chain = _row(ticket_id)
    if not chain:
        return json.dumps({
            "ticket_id": ticket_id,
            "escalations": [],
            "note": f"Ticket {ticket_id} has no escalation history -- it was resolved without escalation.",
        })
    return json.dumps({"ticket_id": ticket_id, "escalations": chain})


if __name__ == "__main__":
    mcp.run(transport="stdio")

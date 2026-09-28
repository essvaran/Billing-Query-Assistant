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

from mcp.server.mcpserver import MCPServer

mcp = MCPServer("ticket-history")

# Synthetic history data keyed by ticket_id
_HISTORY = {
    "T002": {
        "ticket_id": "T002",
        "created": "2025-06-10T09:15:00Z",
        "status_changes": [
            {"from": "open", "to": "in_progress", "at": "2025-06-10T09:30:00Z", "by": "agent-A"},
            {"from": "in_progress", "to": "resolved", "at": "2025-06-10T11:00:00Z", "by": "agent-A"},
        ],
        "assigned_agents": ["agent-A"],
    },
    "T003": {
        "ticket_id": "T003",
        "created": "2025-06-11T14:00:00Z",
        "status_changes": [
            {"from": "open", "to": "in_progress", "at": "2025-06-11T14:20:00Z", "by": "agent-B"},
            {"from": "in_progress", "to": "escalated", "at": "2025-06-11T15:45:00Z", "by": "agent-B"},
        ],
        "assigned_agents": ["agent-B", "agent-C"],
    },
    "T005": {
        "ticket_id": "T005",
        "created": "2025-06-12T08:00:00Z",
        "status_changes": [
            {"from": "open", "to": "in_progress", "at": "2025-06-12T08:10:00Z", "by": "agent-A"},
        ],
        "assigned_agents": ["agent-A"],
    },
    "T008": {
        "ticket_id": "T008",
        "created": "2025-06-13T10:30:00Z",
        "status_changes": [
            {"from": "open", "to": "in_progress", "at": "2025-06-13T10:45:00Z", "by": "agent-D"},
            {"from": "in_progress", "to": "escalated", "at": "2025-06-13T12:00:00Z", "by": "agent-D"},
            {"from": "escalated", "to": "resolved", "at": "2025-06-13T16:30:00Z", "by": "agent-E"},
        ],
        "assigned_agents": ["agent-D", "agent-E"],
    },
}

_ESCALATIONS = {
    "T003": [
        {
            "ticket_id": "T003",
            "escalated_at": "2025-06-11T15:45:00Z",
            "from_agent": "agent-B",
            "to_agent": "agent-C",
            "reason": "Customer requested supervisor review of denied refund",
            "level": 2,
        },
    ],
    "T008": [
        {
            "ticket_id": "T008",
            "escalated_at": "2025-06-13T12:00:00Z",
            "from_agent": "agent-D",
            "to_agent": "agent-E",
            "reason": "Order O208 not found in system -- possible data integrity issue",
            "level": 2,
        },
    ],
}


@mcp.tool()
def lookup_ticket_history(ticket_id: str) -> str:
    """Look up the full lifecycle history of a support ticket by ticket_id
    (format: Tnnn, e.g. T002, T008).

    Returns the creation timestamp, status change timeline, and
    list of assigned agents. If the ticket has no recorded history,
    returns a clear message so you can tell the user rather than
    retrying the same call.
    """
    record = _HISTORY.get(ticket_id)
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
    chain = _ESCALATIONS.get(ticket_id, [])
    if not chain:
        return json.dumps({
            "ticket_id": ticket_id,
            "escalations": [],
            "note": f"Ticket {ticket_id} has no escalation history -- it was resolved without escalation.",
        })
    return json.dumps({"ticket_id": ticket_id, "escalations": chain})


if __name__ == "__main__":
    mcp.run(transport="stdio")

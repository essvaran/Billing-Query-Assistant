"""MCP server wrapping the four billing-support tools.

Exposes get_ticket, get_order, get_customer_tier, and
search_knowledge_base over stdio transport so the agent
discovers them via tools/list at startup.
"""

import json
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from mcp.server.mcpserver import MCPServer

from agent.tools import (
    get_ticket as _get_ticket,
    get_order as _get_order,
    get_customer_tier as _get_customer_tier,
    search_knowledge_base as _search_knowledge_base,
)

mcp = MCPServer("billing-tools")


@mcp.tool()
def get_ticket(ticket_id: str) -> str:
    """Look up a support ticket by ticket_id (format: Tnnn, e.g. T002, T008).

    Returns the ticket text, customer_id, and linked order_id.
    If the ticket is not found, returns a message with the expected ID format
    so you can ask the user to double-check rather than retrying the same call.
    """
    result = _get_ticket(ticket_id)
    return json.dumps(result)


@mcp.tool()
def get_order(order_id: str) -> str:
    """Fetch an order record by order ID (format: Onnn, e.g. O201, O210).

    Returns purchase date, amount, currency, fulfilment status,
    and days_since_purchase. If not found, returns a not_found message
    with the expected format so you can ask the user to verify.
    """
    result = _get_order(order_id)
    return json.dumps(result)


@mcp.tool()
def get_customer_tier(customer_id: str, tier: str = "standard") -> str:
    """Return the SLA tier for a customer account (format: Cnnn, e.g. C101).

    Used to select the applicable refund window. The tier parameter is a
    caller hint only; the record's actual tier is always authoritative.
    If not found, returns a not_found message with the expected format.
    """
    result = _get_customer_tier(customer_id, tier)
    return json.dumps(result)


@mcp.tool()
def search_knowledge_base(query: str, top_k: int = 3) -> str:
    """Search the billing support knowledge base using hybrid retrieval
    (BM25 + dense vector RRF fusion).

    Only call this for an explicit error code (e.g. ERR-4032, PAY-1001) or a named
    policy/migration/procedure question that get_ticket, get_order, and
    get_customer_tier cannot answer. Do NOT call this for ordinary refund requests
    (duplicate charge, wrong amount, order not found) -- resolve those from the
    ticket and order data alone.

    query: a natural-language search string.
    top_k: number of results to return (1-5, default 3).
    """
    result = _search_knowledge_base(query, top_k=top_k)
    return json.dumps(result)


if __name__ == "__main__":
    mcp.run(transport="stdio")

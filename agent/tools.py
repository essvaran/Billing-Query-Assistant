"""Tool implementations and OpenAI-compatible JSON schemas.

Tool 1: get_ticket             -- retrieve a support ticket by ID
Tool 2: get_order              -- fetch an order record by ID
Tool 3: get_customer_tier      -- return the SLA tier for a customer account
Tool 4: search_knowledge_base  -- hybrid RAG search over billing documents

No description overlap: each tool fetches one distinct artifact.
"""

import json
from datetime import date


def _db_get_ticket(ticket_id: str) -> dict | None:
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from api.database import get_db
        with get_db() as conn:
            row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def _db_get_order(order_id: str) -> dict | None:
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from api.database import get_db
        with get_db() as conn:
            row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def _db_get_customer(customer_id: str) -> dict | None:
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from api.database import get_db
        with get_db() as conn:
            row = conn.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


# ---- Python implementations ----

def get_ticket(ticket_id: str) -> dict:
    record = _db_get_ticket(ticket_id)
    if record is None:
        from agent.tickets import TICKETS
        record = TICKETS.get(ticket_id)
    if record is None:
        from agent.tickets import TICKETS
        available = sorted(TICKETS.keys())[:5]
        return {
            "error": "not_found",
            "ticket_id": ticket_id,
            "hint": f"Ticket {ticket_id} not found -- IDs look like Tnnn (e.g. {', '.join(available)}). Ask the user to verify.",
        }
    return dict(record)


def get_order(order_id: str) -> dict:
    record = _db_get_order(order_id)
    if record is None:
        from agent.tickets import ORDERS
        record = ORDERS.get(order_id)
    if record is None:
        return {"error": "not_found", "order_id": order_id}
    purchase = date.fromisoformat(record["purchase_date"])
    days = (date.today() - purchase).days
    return {**record, "days_since_purchase": days}


def search_knowledge_base(query: str, top_k: int = 3, **kwargs) -> dict:
    """Search the billing knowledge base using hybrid retrieval (BM25 + dense RRF)."""
    import sys
    import traceback
    from pathlib import Path
    _root = str(Path(__file__).resolve().parent.parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)
    try:
        from src.retrieval.hybrid_search import hybrid_search
        from src.config import DEFAULT_COLLECTION
        hits = hybrid_search(DEFAULT_COLLECTION, query, top_n=min(int(top_k), 5))
        if not hits:
            return {"query": query, "results": [], "note": "No matching documents found."}
        return {
            "query": query,
            "results": [
                {
                    "rank": h["rank"],
                    "chunk_id": h["chunk_id"],
                    "article_id": h["article_id"],
                    "section": h.get("section"),
                    "score": h["score"],
                    "text": h["text"][:300],
                }
                for h in hits
            ],
        }
    except Exception as exc:
        return {"error": str(exc), "detail": traceback.format_exc()[-600:], "query": query}


def get_customer_tier(customer_id: str, tier: str = "standard") -> dict:
    """Return the authoritative tier record for a customer account.

    The ``tier`` parameter is the caller's expected tier (hint only);
    the record's actual tier is always authoritative.
    """
    record = _db_get_customer(customer_id)
    if record is None:
        from agent.tickets import CUSTOMERS
        record = CUSTOMERS.get(customer_id)
    if record is None:
        return {"error": "not_found", "customer_id": customer_id}
    return dict(record)


# ---- OpenAI-compatible JSON schemas ----

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_ticket",
            "description": (
                "Retrieve a support ticket by its ID and return the ticket text, "
                "customer ID, and linked order ID."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticket_id": {
                        "type": "string",
                        "description": "The ticket identifier, e.g. T001.",
                    }
                },
                "required": ["ticket_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": (
                "Fetch an order record by order ID and return purchase date, "
                "amount, currency, and fulfilment status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The order identifier, e.g. O201.",
                    }
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_tier",
            "description": (
                "Return the service tier assigned to a customer account -- "
                "used exclusively to select the applicable refund window."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "description": "The customer identifier, e.g. C101.",
                    },
                    "tier": {
                        "type": "string",
                        "enum": ["standard", "premium", "enterprise"],
                        "description": (
                            "Caller's expected tier (hint); the authoritative tier "
                            "is always returned from the record."
                        ),
                    },
                },
                "required": ["customer_id", "tier"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Search the billing support knowledge base using hybrid retrieval "
                "(BM25 + dense vector RRF fusion). Use this to look up billing policies, "
                "error code explanations, migration procedures, account roles, or any "
                "question that requires documented knowledge rather than live order/ticket data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A natural language search query, e.g. 'ERR-4032 billing migration error'.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of chunks to return (1-5). Default 3.",
                        "default": 3,
                    },
                },
                "required": ["query"],
            },
        },
    },
]

TOOL_DISPATCH: dict[str, callable] = {
    "get_ticket": get_ticket,
    "get_order": get_order,
    "get_customer_tier": get_customer_tier,
    "search_knowledge_base": search_knowledge_base,
}


def dispatch_tool(name: str, arguments: str) -> str:
    """Execute a tool by name and return its result as a JSON string."""
    fn = TOOL_DISPATCH.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown_tool: {name}"})
    try:
        args = json.loads(arguments)
        result = fn(**args)
        return json.dumps(result)
    except Exception as exc:
        return json.dumps({"error": str(exc)})

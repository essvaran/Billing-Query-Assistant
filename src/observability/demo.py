"""Synthetic incident used for the support drill demo."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.generation.cost import calculate_cost

def _incident() -> dict:
    """The planted incident (setting demo.incident, editable in Admin, Settings)."""
    from src.catalog import settings
    return settings.get("demo.incident")


def yesterday_afternoon():
    """A random-looking time between 12:00 and 18:00 UTC yesterday, as ISO text."""
    base = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=1)
    offset = uuid4().int % (6 * 3600)
    return (base + timedelta(seconds=offset)).isoformat(timespec="seconds")


def build_bad_refund_record(model, trace_id=None, timestamp=None):
    inc = dict(_incident())
    cost = calculate_cost(model, inc["input_tokens"], inc["output_tokens"])["total_cost_usd"]
    inc.pop("user_email", None)
    inc.pop("complaint", None)
    return {
        **inc,
        "trace_id": trace_id or str(uuid4()),
        "timestamp": timestamp or yesterday_afternoon(),
        "original_query": inc["question"],
        "rewritten_query": None,
        "model": model,
        "raw_output": inc["final_answer"],
        "cost_usd": cost,
        "cost_by_stage": {"retrieval_usd": 0.0, "generation_usd": cost, "tools_usd": 0.0},
        "error": None,
    }


def plant_bad_trace(model, trace_id=None, timestamp=None):
    """Create the incident as a real trace in Langfuse (tagged demo-planted). Idempotent for a fixed trace_id."""
    from src.generation import langfuse_client
    from src.observability import trace_store

    lf = langfuse_client.get_langfuse()
    if lf is None:
        raise RuntimeError("Langfuse is not configured, so a demo trace cannot be planted.")
    record = build_bad_refund_record(model, trace_id, timestamp)
    record["user_email"] = _incident().get("user_email", "demo-customer@example.com")
    when = datetime.fromisoformat(record["timestamp"])
    trace = lf.trace(
        id=record["trace_id"],
        name="answer_question",
        user_id=record["user_email"],
        version=record["prompt_version"],
        tags=[f"prompt:{record['prompt_version']}", "demo-planted"],
        timestamp=when,
        input={"question": record["question"]},
        output={"final_answer": record["final_answer"], "reason": None},
        metadata={
            "prompt_version": record["prompt_version"],
            "model": model,
            "retriever": record["retriever"],
            "collection": record["collection"],
            "top_k": record["top_k"],
            "temperature": record["temperature"],
            "citations_valid": record["citations_valid"],
            "citations": record["citations"],
            "unverified": True,
            "retrieved_chunks": record["retrieved_chunks"],
            "retrieval_ms": record["retrieval_ms"],
            "generation_ms": record["generation_ms"],
            "total_ms": record["total_ms"],
            "input_tokens": record["input_tokens"],
            "output_tokens": record["output_tokens"],
            "cost_usd": record["cost_usd"],
            "demo": True,
        },
    )
    cost = calculate_cost(model, record["input_tokens"], record["output_tokens"])
    trace.generation(
        name="llm_call",
        model=model,
        start_time=when - timedelta(milliseconds=record["generation_ms"]),
        end_time=when,
        output=record["raw_output"],
        usage={
            "input": record["input_tokens"],
            "output": record["output_tokens"],
            "unit": "TOKENS",
            "inputCost": cost["input_cost_usd"],
            "outputCost": cost["output_cost_usd"],
            "totalCost": cost["total_cost_usd"],
        },
    )
    lf.flush()
    trace_store.remember(record)
    return record

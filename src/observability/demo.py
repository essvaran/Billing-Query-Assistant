"""Synthetic incident used for the support drill demo."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.generation.cost import calculate_cost

BAD_ANSWER = (
    "Yes, if your billing migration fails you are entitled to a full refund within 30 days. "
    "Contact support with your migration ID and they will return the money to your original "
    "payment method. [HC-BILL-006--when-a-rollback-is-possible--prose-001]"
)


def yesterday_afternoon():
    """A random-looking time between 12:00 and 18:00 UTC yesterday, as ISO text."""
    base = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=1)
    offset = uuid4().int % (6 * 3600)
    return (base + timedelta(seconds=offset)).isoformat(timespec="seconds")


def build_bad_refund_record(model, trace_id=None, timestamp=None):
    input_tokens, output_tokens = 921, 74
    cost = calculate_cost(model, input_tokens, output_tokens)["total_cost_usd"]
    question = "Can I get a refund if my billing migration fails?"
    return {
        "trace_id": trace_id or str(uuid4()),
        "timestamp": timestamp or yesterday_afternoon(),
        "question": question,
        "original_query": question,
        "rewritten_query": None,
        "prompt_version": "v1",
        "model": model,
        "temperature": 0.0,
        "retriever": "hybrid-bm25-rrf",
        "top_k": 3,
        "collection": "billing_structure_aware",
        "retrieved_chunks": [
            {"chunk_id": "HC-BILL-001--related-articles--prose-001", "document_id": "HC-BILL-001", "score": 0.030536, "rank": 1},
            {"chunk_id": "HC-BILL-006--when-a-rollback-is-possible--prose-001", "document_id": "HC-BILL-006", "score": 0.029324, "rank": 2},
            {"chunk_id": "HC-BILL-002--frequently-asked-questions-about-error-codes--prose-001", "document_id": "HC-BILL-002", "score": 0.028034, "rank": 3},
        ],
        "raw_output": BAD_ANSWER,
        "final_answer": BAD_ANSWER,
        "citations": ["hc-bill-006--when-a-rollback-is-possible--prose-001"],
        "citations_valid": False,
        "retrieval_ms": 58.4,
        "generation_ms": 1043.7,
        "total_ms": 1102.1,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost,
        "cost_by_stage": {"retrieval_usd": 0.0, "generation_usd": cost, "tools_usd": 0.0},
        "error": None,
    }


DEMO_USER = "demo-customer@example.com"


def plant_bad_trace(model, trace_id=None, timestamp=None):
    """Create the incident as a real trace in Langfuse (tagged demo-planted). Idempotent for a fixed trace_id."""
    from src.generation import langfuse_client
    from src.observability import trace_store

    lf = langfuse_client.get_langfuse()
    if lf is None:
        raise RuntimeError("Langfuse is not configured, so a demo trace cannot be planted.")
    record = build_bad_refund_record(model, trace_id, timestamp)
    record["user_email"] = DEMO_USER
    when = datetime.fromisoformat(record["timestamp"])
    trace = lf.trace(
        id=record["trace_id"],
        name="answer_question",
        user_id=DEMO_USER,
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

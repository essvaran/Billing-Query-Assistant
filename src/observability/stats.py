"""Cost and latency statistics over traces in the page shape (see trace_store.normalize)."""
import math


def percentile(sorted_values, pct):
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, math.ceil(pct / 100 * len(sorted_values)) - 1))
    return sorted_values[index]


def group_stats(items):
    llm = [i for i in items if (i["generation_ms"] or 0) > 0 or (i["input_tokens"] or 0) > 0]
    n = len(llm)
    costs = sorted(i["cost_usd"] for i in llm)
    gen_values = [i["generation_ms"] for i in llm if i["generation_ms"] is not None]
    ret_values = [i["retrieval_ms"] for i in llm if i["retrieval_ms"] is not None]

    def avg(values):
        return (sum(values) / len(values)) if values else 0.0

    return {
        "requests": len(items),
        "llm_requests": n,
        "avg_cost_usd": round(avg(costs), 8),
        "p50_cost_usd": round(percentile(costs, 50), 8),
        "p95_cost_usd": round(percentile(costs, 95), 8),
        "max_cost_usd": round(costs[-1], 8) if costs else 0.0,
        "avg_input_tokens": round(avg([i["input_tokens"] or 0 for i in llm]), 1),
        "avg_output_tokens": round(avg([i["output_tokens"] or 0 for i in llm]), 1),
        "avg_retrieval_ms": round(avg(ret_values), 1),
        "avg_generation_ms": round(avg(gen_values), 1),
        "p50_retrieval_ms": round(percentile(sorted(ret_values), 50), 1),
        "p50_generation_ms": round(percentile(sorted(gen_values), 50), 1),
        "models": sorted({i["model"] for i in llm if i["model"]}),
        "unverified_answers": sum(1 for i in llm if i["unverified"]),
        "cost_per_1000_usd": round(avg(costs) * 1000, 4),
    }

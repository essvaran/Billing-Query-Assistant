"""Token-to-USD cost calculation for LLM calls. Prices come from the catalog (Admin, Model prices)."""
from src.catalog import prices


def calculate_cost(model, input_tokens, output_tokens):
    p = prices.for_model(model)
    input_cost = input_tokens * p["input_per_1m"] / 1_000_000
    output_cost = output_tokens * p["output_per_1m"] / 1_000_000
    return {
        "input_cost_usd": round(input_cost, 8),
        "output_cost_usd": round(output_cost, 8),
        "total_cost_usd": round(input_cost + output_cost, 8),
    }


def cost_of_usage(model, usage: dict | None) -> float:
    """Cost of one provider response from its usage block (prompt and completion tokens priced separately)."""
    usage = usage or {}
    return calculate_cost(model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))["total_cost_usd"]

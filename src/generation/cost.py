"""Token-to-USD cost calculation for LLM calls."""

# USD per 1M tokens. Verify against the provider price page before relying on absolutes.
PRICING = {
    "llama-3.1-8b-instant": {"input_per_1m": 0.05, "output_per_1m": 0.08},
    "openai/gpt-oss-20b": {"input_per_1m": 0.075, "output_per_1m": 0.30},
    "openai/gpt-oss-120b": {"input_per_1m": 0.15, "output_per_1m": 0.60},
    "default": {"input_per_1m": 0.05, "output_per_1m": 0.08},
}


def calculate_cost(model, input_tokens, output_tokens):
    prices = PRICING.get(model, PRICING["default"])
    input_cost = input_tokens * prices["input_per_1m"] / 1_000_000
    output_cost = output_tokens * prices["output_per_1m"] / 1_000_000
    return {
        "input_cost_usd": round(input_cost, 8),
        "output_cost_usd": round(output_cost, 8),
        "total_cost_usd": round(input_cost + output_cost, 8),
    }

"""Cost per query by stage, from traces in Langfuse (the newest LANGFUSE_SCAN_LIMIT * 2 in the window).

Usage:
    python scripts/cost_analysis.py
    python scripts/cost_analysis.py --days 30 --prompt-version v2
    python scripts/cost_analysis.py --model openai/gpt-oss-120b
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.generation.cost import PRICING
from src.observability import trace_store
from src.observability.stats import group_stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--prompt-version")
    parser.add_argument("--model", help="restrict to one model")
    args = parser.parse_args()

    try:
        items, incomplete = trace_store.recent_window(args.days)
    except trace_store.TraceStoreError as exc:
        sys.exit(f"error: {exc.message}")
    if args.prompt_version:
        items = [i for i in items if i["prompt_version"] == args.prompt_version]
    if args.model:
        items = [i for i in items if i["model"] == args.model]
    stats = group_stats(items)
    if not stats["llm_requests"]:
        print("no LLM-calling traces matched")
        return

    note = "(older traces in the window were not scanned)" if incomplete else ""
    print(f"LLM-calling requests analysed: {stats['llm_requests']} {note}")
    print(f"Models: {stats['models']}")
    print(f"Avg input tokens: {stats['avg_input_tokens']:.0f}   Avg output tokens: {stats['avg_output_tokens']:.0f}")
    print(f"Median retrieval ms: {stats['p50_retrieval_ms']:.1f}   Median generation ms: {stats['p50_generation_ms']:.1f}")
    print()
    print("| Stage | Cost per query (USD) |")
    print("|---|---|")
    print("| Retrieval (local ChromaDB + BM25, no API) | 0.00000000 |")
    print(f"| Generation (LLM tokens) | {stats['avg_cost_usd']:.8f} |")
    print("| Tools (none called in this pipeline) | 0.00000000 |")
    print(f"| **Total** | **{stats['avg_cost_usd']:.8f}** |")
    print()
    print(f"median={stats['p50_cost_usd']:.8f}  p95={stats['p95_cost_usd']:.8f}  max={stats['max_cost_usd']:.8f}")
    print(f"per 1,000 queries: ${stats['cost_per_1000_usd']:.4f}")
    print(f"pricing table in use: {PRICING}")


if __name__ == "__main__":
    main()

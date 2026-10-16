"""Search traces in Langfuse (the only trace store). Built for the support drill.

Langfuse filters time, user, prompt version and name itself. Keyword, cost and unverified filters are
applied here on the newest traces fetched, so they cover the latest LANGFUSE_SCAN_LIMIT traces.

Examples:
    python scripts/search_traces.py --after "2026-10-11 12:00" --before "2026-10-11 18:00" --keyword refund
    python scripts/search_traces.py --bad-citations
    python scripts/search_traces.py --cost-above 0.0001 --prompt-version v1
    python scripts/search_traces.py --user alice@example.com
    python scripts/search_traces.py --trace-id <uuid> --json
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.observability import trace_store


def _iso(value):
    return value.replace(" ", "T") + ("Z" if "+" not in value and not value.endswith("Z") else "") if value else None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trace-id")
    parser.add_argument("--after", help="UTC, for example '2026-10-11 12:00'")
    parser.add_argument("--before", help="UTC")
    parser.add_argument("--keyword")
    parser.add_argument("--prompt-version")
    parser.add_argument("--user")
    parser.add_argument("--cost-above", type=float)
    parser.add_argument("--bad-citations", action="store_true",
                        help="non-refusal answers whose citations did not validate")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="print full rows as JSON")
    args = parser.parse_args()

    try:
        if args.trace_id:
            item = trace_store.get_trace(args.trace_id)
            rows, note = ([item] if item else []), ""
        else:
            result = trace_store.search({
                "after": _iso(args.after), "before": _iso(args.before), "keyword": args.keyword,
                "prompt_version": args.prompt_version, "user": args.user, "cost_above": args.cost_above,
                "unverified": args.bad_citations,
            }, args.limit, 0)
            rows = result["items"]
            note = f" (scanned the newest {result['scanned']}{', more exist' if result['truncated'] else ''})"
    except trace_store.TraceStoreError as exc:
        sys.exit(f"error: {exc.message}")

    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return
    print(f"{len(rows)} trace(s){note}")
    for r in rows:
        print(
            f"{r['timestamp']}  {r['trace_id']}  pv={r['prompt_version']}  "
            f"cost=${r['cost_usd']:.8f}  unverified={r['unverified']}  user={r['user_email']}\n"
            f"  Q: {r['question'][:90]}\n  A: {r['final_answer'][:110]}"
        )


if __name__ == "__main__":
    main()

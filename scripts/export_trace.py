"""Print and export one end-to-end trace: every span, with cost and latency, across the API,
the agent and both MCP servers.

Run:  python scripts/export_trace.py <trace_id> [--out docs/archive/deliverables/week12/trace.json]
      python scripts/export_trace.py --latest
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tier1 import db, tracing_store


def _latest_trace_id() -> str | None:
    with db.get_conn() as conn:
        row = conn.execute("SELECT trace_id FROM spans WHERE parent_id IS NULL ORDER BY started_at DESC LIMIT 1").fetchone()
    return row["trace_id"] if row else None


def _print_tree(nodes: list[dict], t0: datetime, depth: int = 0) -> None:
    for n in nodes:
        offset = (datetime.fromisoformat(n["started_at"]) - t0).total_seconds() * 1000
        tokens = f"{n['input_tokens'] or 0}+{n['output_tokens'] or 0}tok" if n["kind"] == "llm" else ""
        cost = f"${n['cost_usd']:.6f}" if n["cost_usd"] else ""
        extra = []
        if n["kind"] == "llm":
            a = n["attrs"]
            extra.append(f"cache={a.get('cache')} waited={a.get('waited_s', 0)}s")
        flag = "" if n["status"] == "ok" else "  [ERROR]"
        label = f"{'  ' * depth}{n['name']}"
        print(f"{label:<44} {n['kind']:<10} +{offset:>8.0f}ms {n['duration_ms']:>9.1f}ms {tokens:<14} {cost:<11} {' '.join(extra)}{flag}")
        _print_tree(n["children"], t0, depth + 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("trace_id", nargs="?")
    ap.add_argument("--latest", action="store_true")
    ap.add_argument("--out", help="write the full trace as JSON")
    args = ap.parse_args()

    trace_id = args.trace_id or (_latest_trace_id() if args.latest else None)
    if not trace_id:
        print("give a trace id or --latest", file=sys.stderr)
        return 2
    spans = tracing_store.get_spans(trace_id)
    if not spans:
        print(f"no spans for {trace_id}", file=sys.stderr)
        return 1

    summary = tracing_store.summarize(spans)
    nodes = tracing_store.tree(spans)
    t0 = datetime.fromisoformat(min(s["started_at"] for s in spans))
    print(f"trace {trace_id}\n")
    _print_tree(nodes, t0)
    print(f"\nsummary: {json.dumps(summary)}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"summary": summary, "spans": spans, "tree": nodes}, indent=2), encoding="utf-8")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

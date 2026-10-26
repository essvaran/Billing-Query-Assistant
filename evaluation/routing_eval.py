"""How often the chat front desk (src/routing/route.py) sends a question where it belongs.

Labels come from where each question already lives:
  docs   Docs-mode eval questions (evaluation/eval_set.jsonl, evaluation/golden_set.jsonl)
  agent  Tier-1 tickets (evaluation/integrated/cases.jsonl, cases_holdout.jsonl)
  both   hand-written paraphrases with no codes or obvious keywords (evaluation/routing_cases.jsonl)

Every question is routed as a user WITH an account, so the fallback is the assistant.

    python evaluation/routing_eval.py          rules only, no model calls (free, deterministic)
    python evaluation/routing_eval.py --llm    unsure questions go to the classifier, as in the app
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.routing.route import decide_route

EVAL = Path(__file__).resolve().parent


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def cases() -> list[dict]:
    out, seen = [], set()

    def add(text, expect, origin):
        if text and text not in seen:
            seen.add(text)
            out.append({"text": text, "expect": expect, "origin": origin})

    for name in ("eval_set.jsonl", "golden_set.jsonl"):
        for row in _jsonl(EVAL / name):
            add(row["question"], "docs", name)
    for name in ("cases.jsonl", "cases_holdout.jsonl"):
        for row in _jsonl(EVAL / "integrated" / name):
            add(f"{row.get('subject') or ''}\n{row['body']}".strip(), "agent", f"integrated/{name}")
    for row in _jsonl(EVAL / "routing_cases.jsonl"):
        add(row["text"], row["expect"], "routing_cases.jsonl")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--llm", action="store_true", help="let unsure questions reach the classifier")
    args = parser.parse_args()

    if not args.llm:
        import src.routing.route as route
        route._setting = lambda key, _real=route._setting: False if key == "routing.use_llm" else _real(key)

    rows = cases()
    misses, sources = [], Counter()
    for c in rows:
        d = decide_route(c["text"], has_account=True)
        sources[d.source] += 1
        if d.route != c["expect"]:
            misses.append({**c, "got": d.route, "source": d.source, "reason": d.reason})

    total = len(rows)
    print(f"Routing accuracy: {total - len(misses)}/{total} = {(total - len(misses)) / total:.1%}"
          f"  ({'rules + model' if args.llm else 'rules only, no model calls'})")
    print("Decided by: " + ", ".join(f"{k} {v}" for k, v in sources.most_common()))
    for m in misses:
        print(f"  MISS expect={m['expect']} got={m['got']} ({m['source']}: {m['reason']})  {m['text'][:90]!r}  [{m['origin']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

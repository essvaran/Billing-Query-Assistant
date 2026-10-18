"""Sample 20 traces from evaluation/traces.jsonl using a fixed random seed.

Only traces that used the hybrid BM25+RRF retriever are eligible for sampling.
Writes the sampled traces to evaluation/sample.jsonl so the same 20 traces
can be loaded by the API and the Sample Viewer UI without re-running the
random selection every time.

Usage:
    python scripts/sample_traces.py
"""
import json
import random
from pathlib import Path

TRACES_PATH = Path(__file__).resolve().parents[1] / "evaluation" / "traces.jsonl"
SAMPLE_PATH = Path(__file__).resolve().parents[1] / "evaluation" / "sample.jsonl"
import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.catalog import settings  # noqa: E402

SEED = settings.get("docs.sample_seed")          # Admin, Settings, Docs mode retrieval
SAMPLE_SIZE = settings.get("docs.sample_size")
REQUIRED_RETRIEVER = "hybrid-bm25-rrf"

_CODE_PATTERN = __import__("re").compile(r"\b[A-Z]{2,}-[A-Z0-9]{2,}(?:-[A-Z0-9]+)+\b")


def classify_query_type(question: str) -> str:
    """Classify a question into a Docs query type (the API's own classifier; word lists are catalog list query_type)."""
    from api.main import _classify_query_type
    return _classify_query_type(question)


def main() -> None:
    if not TRACES_PATH.exists():
        print(f"ERROR: No traces file at {TRACES_PATH}")
        print("Run:   python scripts/generate_traces.py  first.")
        return

    all_traces: list[dict] = []
    for line in TRACES_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    all_traces.append(parsed)
            except json.JSONDecodeError:
                pass

    print(f"Total traces in file : {len(all_traces)}")

    # Show retriever breakdown
    retriever_counts: dict[str, int] = {}
    for t in all_traces:
        r = t.get("retriever", "unknown")
        retriever_counts[r] = retriever_counts.get(r, 0) + 1
    for retriever, count in sorted(retriever_counts.items()):
        marker = " ✓ (eligible)" if retriever == REQUIRED_RETRIEVER else " ✗ (excluded)"
        print(f"  {retriever:30} {count:4d} traces{marker}")

    # Filter to hybrid-only
    eligible = [t for t in all_traces if t.get("retriever") == REQUIRED_RETRIEVER]
    excluded = len(all_traces) - len(eligible)

    if excluded > 0:
        print(f"\nExcluded {excluded} non-hybrid trace(s) from the sampling pool.")

    print(f"Eligible (hybrid)    : {len(eligible)}")

    if len(eligible) == 0:
        print("\nERROR: No hybrid traces found. Run generate_traces.py first.")
        return

    if len(eligible) < SAMPLE_SIZE:
        print(f"WARNING: only {len(eligible)} hybrid traces — sampling all of them")
        sample = eligible[:]
    else:
        random.seed(SEED)
        sample = random.sample(eligible, SAMPLE_SIZE)

    SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SAMPLE_PATH.open("w", encoding="utf-8") as f:
        for t in sample:
            t["query_type"] = classify_query_type(t.get("question", ""))
            f.write(json.dumps(t) + "\n")

    print(f"\nSampled {len(sample)} traces  (seed={SEED}, retriever={REQUIRED_RETRIEVER})")
    print(f"Written to           : {SAMPLE_PATH}\n")

    w = 52
    print(f"{'#':>3}  {'trace_id':36}  {'citations':10}  question")
    print("-" * (3 + 2 + 36 + 2 + 10 + 2 + w))
    for i, t in enumerate(sample, 1):
        valid = "valid" if t.get("citations_valid") else "INVALID"
        print(f"{i:>3}  {t['trace_id']}  {valid:10}  {t['question'][:w]}")


if __name__ == "__main__":
    main()

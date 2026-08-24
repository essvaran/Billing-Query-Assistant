"""Sample 20 traces from evaluation/traces.jsonl using a fixed random seed.

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
SEED = 42
SAMPLE_SIZE = 20


def main() -> None:
    if not TRACES_PATH.exists():
        print(f"ERROR: No traces file at {TRACES_PATH}")
        print("Run:   python scripts/generate_traces.py  first.")
        return

    traces: list[dict] = []
    for line in TRACES_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    traces.append(parsed)
            except json.JSONDecodeError:
                pass

    print(f"Total traces in file : {len(traces)}")

    if len(traces) < SAMPLE_SIZE:
        print(f"WARNING: only {len(traces)} traces available — sampling all of them")
        sample = traces[:]
    else:
        random.seed(SEED)
        sample = random.sample(traces, SAMPLE_SIZE)

    SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SAMPLE_PATH.open("w", encoding="utf-8") as f:
        for t in sample:
            f.write(json.dumps(t) + "\n")

    print(f"Sampled {len(sample)} traces  (seed={SEED})")
    print(f"Written to           : {SAMPLE_PATH}\n")

    w = 55
    print(f"{'#':>3}  {'trace_id':36}  {'citations':10}  question")
    print("-" * (3 + 2 + 36 + 2 + 10 + 2 + w))
    for i, t in enumerate(sample, 1):
        valid = "valid" if t.get("citations_valid") else "INVALID"
        print(f"{i:>3}  {t['trace_id']}  {valid:10}  {t['question'][:w]}")


if __name__ == "__main__":
    main()

"""Plant one bad refund answer (yesterday afternoon) for the support drill.

The corpus has no refund policy, so a correct system refuses. This trace is the
failure the customer complained about: a confident, fabricated refund answer.

Usage:
    python scripts/plant_bad_trace.py
    python scripts/plant_bad_trace.py --timestamp 2026-10-11T14:32:17+00:00
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.generation.llm_client import default_model
from src.observability.demo import plant_bad_trace

PLANTED_TRACE_ID = "8ebfc75d-5499-4c3f-b606-2bb07a201a7c"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timestamp", default="2026-10-11T14:32:17+00:00")
    args = parser.parse_args()

    record = plant_bad_trace(default_model(), PLANTED_TRACE_ID, args.timestamp)  # re-running is a no-op
    print(f"planted trace_id={record['trace_id']} at {record['timestamp']}")


if __name__ == "__main__":
    main()

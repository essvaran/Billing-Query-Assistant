"""Run ONE eval case through the live pipeline and print PASS/FAIL (fast RED/GREEN demo).

Usage:
    python scripts/check_case.py G07
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.assertions import run_assertions
from src.generation.answer import PROMPT_VERSION, answer_question

EVAL_SET = Path(__file__).resolve().parents[1] / "evaluation" / "eval_set.jsonl"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_id")
    args = parser.parse_args()

    cases = [json.loads(l) for l in EVAL_SET.read_text(encoding="utf-8").splitlines() if l.strip()]
    case = next((c for c in cases if c["case_id"] == args.case_id), None)
    if case is None:
        sys.exit(f"unknown case_id {args.case_id}")

    ans = answer_question(case["question"])
    checks = run_assertions(
        ans.final_answer, [c["chunk_id"] for c in ans.retrieved_chunks], case.get("expected_behavior")
    )
    print(f"prompt_version={PROMPT_VERSION}  case={case['case_id']}  expected={case['expected_behavior']}")
    print(f"answer: {ans.final_answer[:200]}")
    for c in checks:
        print(f"  {'PASS' if c.passed else 'FAIL'}  {c.name}: {c.detail}")
    ok = all(c.passed for c in checks)
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

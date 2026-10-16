"""Week 6 evaluation runner.

Usage
-----
# Phase 1 -- generate answers for blind labeling (do this FIRST):
    python evaluation/run_eval.py --generate-only

  This writes evaluation/answers_25.jsonl.
  Read each answer, label it GOOD / NOT_GOOD in evaluation/labels_25.json,
  then commit labels_25.json BEFORE running the judge.

# Phase 2 -- full eval (assertions + judge + agreement):
    python evaluation/run_eval.py
    python evaluation/run_eval.py --judge-version v2    # run v2 judge
    python evaluation/run_eval.py --all-judges          # run both v1 and v2

# Phase 3 -- push results to Langfuse dashboard:
    python evaluation/run_eval.py --skip-generate --push-langfuse
    python evaluation/run_eval.py --skip-generate --all-judges --push-langfuse
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.generation.answer import answer_question

_EVAL_DIR = Path(__file__).resolve().parent
_EVAL_SET = _EVAL_DIR / "eval_set.jsonl"
_ANSWERS_OUT = _EVAL_DIR / "answers_25.jsonl"
_LABELS = _EVAL_DIR / "labels_25.json"


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_jsonl(path: Path) -> list:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _save_jsonl(rows: list, path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _pct(n: int, d: int) -> str:
    return f"{100*n//d}%" if d else "—"


# ── generate ──────────────────────────────────────────────────────────────────

def generate_answers(cases: list) -> list:
    results = []
    for i, case in enumerate(cases, 1):
        if i > 1:
            time.sleep(5)  # pace Groq RPM limit between calls
        cid = case["case_id"]
        q = case["question"]
        print(f"  [{i:2}/{len(cases)}] {cid}: {q[:60]}...", end="", flush=True)
        try:
            ans = answer_question(q)
            row = {
                "case_id": cid,
                "question": q,
                "mode": case["mode"],
                "expected_behavior": case.get("expected_behavior"),
                "is_regression": case.get("is_regression", False),
                "final_answer": ans.final_answer,
                "raw_answer": ans.raw_answer,
                "citations_valid": ans.citations_valid,
                "retrieved_chunk_ids": [c["chunk_id"] for c in ans.retrieved_chunks],
                "retrieved_chunks": [
                    {"chunk_id": c["chunk_id"], "text": c.get("text", "")[:600]}
                    for c in ans.retrieved_chunks
                ],
                "retrieval_ms": round(ans.retrieval_ms, 1),
                "generation_ms": round(ans.generation_ms, 1),
            }
            print(" ✓")
        except Exception as exc:
            print(f" ERROR: {exc}")
            row = {
                "case_id": cid,
                "question": q,
                "mode": case["mode"],
                "expected_behavior": case.get("expected_behavior"),
                "is_regression": case.get("is_regression", False),
                "final_answer": f"ERROR: {exc}",
                "raw_answer": "",
                "citations_valid": False,
                "retrieved_chunk_ids": [],
                "retrieved_chunks": [],
                "retrieval_ms": 0.0,
                "generation_ms": 0.0,
            }
        results.append(row)
    return results


# ── assertions ────────────────────────────────────────────────────────────────

def run_all_assertions(results: list) -> list:
    from evaluation.assertions import run_assertions
    for row in results:
        checks = run_assertions(row["final_answer"], row["retrieved_chunk_ids"], row.get("expected_behavior"))
        row["assertions"] = {r.name: {"passed": r.passed, "detail": r.detail} for r in checks}
        row["all_assertions_pass"] = all(r.passed for r in checks)
    return results


# ── judge ─────────────────────────────────────────────────────────────────────

def run_judge(results: list, version: str) -> list:
    from evaluation.judge import judge_response
    print(f"\nRunning judge ({version}) on {len(results)} cases…")
    for i, row in enumerate(results, 1):
        if i > 1:
            time.sleep(5)  # pace Groq RPM limit between calls
        print(f"  [{i:2}/{len(results)}] {row['case_id']}", end="", flush=True)
        try:
            verdict = judge_response(
                row["question"],
                row["final_answer"],
                row["retrieved_chunks"],
                version=version,
            )
        except Exception as exc:
            verdict = f"ERROR:{exc}"
        row[f"judge_{version}"] = verdict
        print(f" → {verdict}")
    return results


# ── reporting ─────────────────────────────────────────────────────────────────

def print_assertion_table(results: list) -> None:
    ASSERTION_NAMES = [
        "no_bare_article_id",
        "no_en_dash_in_citation",
        "no_hallucinated_error_code",
        "no_fabricated_citation",
        "refuses_corpus_gap",
    ]
    modes = sorted({r["mode"] for r in results})

    header = f"{'Mode':<26} {'N':>3}  {'bare_id':>7}  {'en_dash':>7}  {'halluc':>6}  {'fabricat':>8}  {'refusal':>7}  {'All':>5}"
    print("\n" + "=" * len(header))
    print("ASSERTION RESULTS")
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    total_n = len(results)
    total_pass = {name: 0 for name in ASSERTION_NAMES}
    total_all = 0

    for mode in modes:
        rows = [r for r in results if r["mode"] == mode]
        n = len(rows)
        cols = []
        for name in ASSERTION_NAMES:
            passed = sum(1 for r in rows if r.get("assertions", {}).get(name, {}).get("passed", False))
            total_pass[name] += passed
            cols.append(f"{passed}/{n}")
        all_pass = sum(1 for r in rows if r.get("all_assertions_pass", False))
        total_all += all_pass
        print(f"  {mode:<24} {n:>3}  {cols[0]:>7}  {cols[1]:>7}  {cols[2]:>6}  {cols[3]:>8}  {cols[4]:>7}  {all_pass}/{n}")

    print("-" * len(header))
    total_cols = [f"{total_pass[name]}/{total_n}" for name in ASSERTION_NAMES]
    print(f"  {'TOTAL':<24} {total_n:>3}  {total_cols[0]:>7}  {total_cols[1]:>7}  {total_cols[2]:>6}  {total_cols[3]:>8}  {total_cols[4]:>7}  {total_all}/{total_n} ({_pct(total_all, total_n)})")


def print_judge_table(results: list, version: str) -> None:
    key = f"judge_{version}"
    modes = sorted({r["mode"] for r in results})

    print(f"\n{'=' * 60}")
    print(f"JUDGE RESULTS ({version})")
    print("=" * 60)
    print(f"{'Mode':<26} {'N':>3}  {'GOOD':>6}  {'Pass%':>6}")
    print("-" * 46)

    total_n = 0
    total_good = 0

    for mode in modes:
        rows = [r for r in results if r["mode"] == mode]
        n = len(rows)
        good = sum(1 for r in rows if r.get(key) == "GOOD")
        total_n += n
        total_good += good
        print(f"  {mode:<24} {n:>3}  {good:>6}  {_pct(good, n):>6}")

    print("-" * 46)
    print(f"  {'TOTAL':<24} {total_n:>3}  {total_good:>6}  {_pct(total_good, total_n):>6}")


def print_agreement(results: list, labels: list, version: str) -> None:
    label_map = {row["case_id"]: row["label"] for row in labels}
    judge_key = f"judge_{version}"

    matched = 0
    total = 0
    mismatches = []

    for row in results:
        cid = row["case_id"]
        human = label_map.get(cid)
        machine = row.get(judge_key)
        if human and machine and not machine.startswith("ERROR"):
            total += 1
            if human == machine:
                matched += 1
            else:
                mismatches.append((cid, human, machine))

    print(f"\n{'=' * 60}")
    print(f"AGREEMENT — labels_25.json vs judge_{version}")
    print("=" * 60)
    print(f"Agreement: {matched}/{total} = {_pct(matched, total)}")

    if mismatches:
        print(f"\nMismatches ({len(mismatches)}):")
        for cid, human, machine in mismatches:
            print(f"  {cid}: human={human}, judge={machine}")


def print_pass_rate_summary(results: list, version: str) -> None:
    judge_key = f"judge_{version}"
    modes = sorted({r["mode"] for r in results})

    print(f"\n{'=' * 60}")
    print("PASS RATE BY MODE (assertions AND judge both pass)")
    print("=" * 60)
    print(f"{'Mode':<26} {'N':>3}  {'Pass':>5}  {'%':>5}")
    print("-" * 44)

    total_n = 0
    total_pass = 0

    for mode in modes:
        rows = [r for r in results if r["mode"] == mode]
        n = len(rows)
        passed = sum(
            1 for r in rows
            if r.get("all_assertions_pass") and r.get(judge_key) == "GOOD"
        )
        total_n += n
        total_pass += passed
        print(f"  {mode:<24} {n:>3}  {passed:>5}  {_pct(passed, n):>5}")

    print("-" * 44)
    print(f"  {'TOTAL':<24} {total_n:>3}  {total_pass:>5}  {_pct(total_pass, total_n):>5}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Week 6 evaluation runner")
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="Generate answers and save to answers_25.jsonl, then stop (for blind labeling).",
    )
    parser.add_argument(
        "--judge-version",
        default="v1",
        choices=["v1", "v2"],
        help="Which judge prompt file to use (default: v1).",
    )
    parser.add_argument(
        "--skip-generate",
        action="store_true",
        help="Load existing answers_25.jsonl instead of re-generating.",
    )
    parser.add_argument(
        "--all-judges",
        action="store_true",
        help="Run both v1 and v2 judges in one pass.",
    )
    parser.add_argument(
        "--push-langfuse",
        action="store_true",
        help="Push all eval results (judges, assertions, RAGAS if available) to Langfuse.",
    )
    args = parser.parse_args()

    cases = _load_jsonl(_EVAL_SET)
    print(f"Loaded {len(cases)} cases from eval_set.jsonl")

    # ── generate ──
    if args.skip_generate:
        if not _ANSWERS_OUT.exists():
            print(f"ERROR: {_ANSWERS_OUT} not found. Run without --skip-generate first.")
            sys.exit(1)
        results = _load_jsonl(_ANSWERS_OUT)
        print(f"Loaded {len(results)} existing answers from answers_25.jsonl")
    else:
        print(f"\nGenerating answers for {len(cases)} cases…")
        results = generate_answers(cases)
        _save_jsonl(results, _ANSWERS_OUT)
        print(f"\nAnswers saved → {_ANSWERS_OUT}")

    if args.generate_only:
        print("\n" + "=" * 60)
        print("BLIND LABELING STEP")
        print("=" * 60)
        print("Read evaluation/answers_25.jsonl and create evaluation/labels_25.json:")
        print()
        print('  [')
        print('    {"case_id": "R01", "label": "GOOD",     "notes": "..."},')
        print('    {"case_id": "R02", "label": "NOT_GOOD", "notes": "..."},')
        print('    ...')
        print('  ]')
        print()
        print("Label each case GOOD or NOT_GOOD based on answer quality only.")
        print("Commit labels_25.json to git BEFORE running the judge.")
        print()
        print("When done:  python evaluation/run_eval.py --skip-generate")
        return

    # ── assertions ──
    print("\nRunning deterministic assertions…")
    results = run_all_assertions(results)
    print_assertion_table(results)

    # ── judge ──
    versions_to_run = ["v1", "v2"] if args.all_judges else [args.judge_version]
    for version in versions_to_run:
        results = run_judge(results, version)
        print_judge_table(results, version)

    # ── save enriched results ──
    _save_jsonl(results, _ANSWERS_OUT)

    # ── agreement (if labels exist) ──
    labels = []
    if _LABELS.exists():
        labels = json.loads(_LABELS.read_text(encoding="utf-8"))
        for version in versions_to_run:
            print_agreement(results, labels, version)
    else:
        print(f"\n[INFO] {_LABELS} not found -- skipping agreement measurement.")
        print("       Create labels_25.json (see --generate-only output) and re-run.")

    for version in versions_to_run:
        print_pass_rate_summary(results, version)

    # ── save predictions ──
    for version in versions_to_run:
        pred_path = _EVAL_DIR / f"prediction_{version}.json"
        judge_key = f"judge_{version}"
        preds = [
            {"case_id": r["case_id"], "label": r.get(judge_key, "ERROR"), "mode": r["mode"]}
            for r in results
        ]
        pred_path.write_text(json.dumps(preds, indent=2), encoding="utf-8")
        print(f"\nJudge predictions saved -> {pred_path}")

    # ── merge RAGAS scores if ragas_results.json exists ──
    ragas_path = _EVAL_DIR / "ragas_results.json"
    if ragas_path.exists():
        ragas_data = json.loads(ragas_path.read_text(encoding="utf-8"))
        ragas_map = {r["case_id"]: r for r in ragas_data}
        for row in results:
            src = ragas_map.get(row["case_id"], {})
            row["ragas_faithfulness"] = src.get("ragas_faithfulness")
            row["ragas_answer_relevancy"] = src.get("ragas_answer_relevancy")
        print(f"\n[RAGAS] Merged scores from {ragas_path.name} into results.")

    # ── push to Langfuse ──
    if args.push_langfuse:
        from evaluation.langfuse_reporter import push_eval_results
        active_versions = [v for v in ("v1", "v2") if any(f"judge_{v}" in r for r in results)]
        push_eval_results(results, judge_versions=active_versions)


if __name__ == "__main__":
    main()

"""Run the billing-support eval as a Langfuse Dataset Experiment.

What this creates in Langfuse:
  Dataset: "billing-eval-25"
    25 items -- each item is one eval case
      input          = {"question": "..."}
      expected_output = {"label": "GOOD" | "NOT_GOOD"}  (from labels_25.json)

  Dataset Run: one named run per execution
    Each item gets a linked Trace with scores:
      judge_v1 / judge_v2   (1=GOOD, 0=NOT_GOOD)
      human_label            (1=GOOD, 0=NOT_GOOD)
      all_assertions_pass    (1 or 0)
      no_bare_article_id     (1 or 0)
      no_en_dash_in_citation (1 or 0)
      no_hallucinated_error_code (1 or 0)
      no_fabricated_citation (1 or 0)
      overall_pass           (1 if assertions AND judge both pass)
      ragas_faithfulness     (0..1, if ragas_results.json exists)
      ragas_answer_relevancy (0..1, if ragas_results.json exists)

Usage
-----
    python evaluation/langfuse_dataset_eval.py
    python evaluation/langfuse_dataset_eval.py --run-name "week6-v2" --judge-version v2
    python evaluation/langfuse_dataset_eval.py --all-judges

In Langfuse UI:
    Datasets > billing-eval-25 > Runs  -- see each run and compare scores per item
    Scores                             -- distribution of every metric
    Sessions / Traces                  -- drill into individual cases
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

_EVAL_DIR = Path(__file__).resolve().parent
_EVAL_SET = _EVAL_DIR / "eval_set.jsonl"
_ANSWERS = _EVAL_DIR / "answers_25.jsonl"
_LABELS = _EVAL_DIR / "labels_25.json"
_RAGAS = _EVAL_DIR / "ragas_results.json"
_DATASET_NAME = "billing-eval-25"


# ── loaders ──────────────────────────────────────────────────────────────────

def _load_jsonl(path: Path) -> list:
    with path.open(encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _load_json(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8"))


# ── dataset setup ─────────────────────────────────────────────────────────────

def ensure_dataset(lf, labels: list) -> None:
    """Create dataset and upsert all 25 items (safe to run multiple times)."""
    label_map = {r["case_id"]: r["label"] for r in labels}

    try:
        lf.create_dataset(
            name=_DATASET_NAME,
            description="25-case billing-support RAG evaluation set (Week 6)",
        )
        print(f"  Dataset '{_DATASET_NAME}' created (or already exists).")
    except Exception:
        pass  # already exists

    from src.catalog import eval_store
    cases = eval_store.cases("docs")   # the Docs eval set lives in the catalog (Admin, Eval cases)
    for case in cases:
        human = label_map.get(case["case_id"])
        lf.create_dataset_item(
            dataset_name=_DATASET_NAME,
            id=case["case_id"],               # stable id -- Langfuse deduplicates
            input={"question": case["question"]},
            expected_output={"label": human, "expected_behavior": case.get("expected_behavior")},
            metadata={
                "mode": case["mode"],
                "is_regression": case.get("is_regression", False),
                "notes": case.get("notes", ""),
            },
        )
    print(f"  {len(cases)} dataset items upserted.")


# ── run experiment ────────────────────────────────────────────────────────────

def run_experiment(
    lf,
    answers: list,
    labels: list,
    judge_versions: list[str],
    run_name: str,
    ragas_map: dict,
) -> None:
    """Create one dataset run: link each answer to its dataset item + score it."""
    from evaluation.assertions import run_assertions
    from evaluation.judge import judge_response

    label_map = {r["case_id"]: r["label"] for r in labels}
    answer_map = {r["case_id"]: r for r in answers}

    dataset = lf.get_dataset(_DATASET_NAME)
    total = len(dataset.items)
    print(f"\n  Running experiment '{run_name}' on {total} dataset items...")

    for idx, item in enumerate(dataset.items, 1):
        cid = item.id
        row = answer_map.get(cid)
        if not row:
            print(f"  [{idx:2}/{total}] {cid}: no answer found -- skipping")
            continue

        print(f"  [{idx:2}/{total}] {cid}", end="", flush=True)

        # ── create trace ──
        try:
            trace = lf.trace(
                name="billing_eval_case",
                input={"question": row["question"]},
                output={"final_answer": row["final_answer"]},
                tags=[row.get("mode", ""), cid],
                metadata={
                    "case_id": cid,
                    "mode": row.get("mode", ""),
                    "expected_behavior": row.get("expected_behavior", ""),
                    "is_regression": row.get("is_regression", False),
                    "retrieval_ms": row.get("retrieval_ms", 0),
                    "generation_ms": row.get("generation_ms", 0),
                    "retrieved_chunk_ids": row.get("retrieved_chunk_ids", []),
                },
            )
        except Exception as exc:
            print(f" ERROR creating trace: {exc}")
            continue

        # ── link trace to dataset item + run ──
        try:
            item.link(
                trace,
                run_name,
                run_description=f"judges={','.join(judge_versions)}",
            )
        except Exception as exc:
            print(f" [warn] link failed: {exc}")

        def _score(name: str, value: float, comment: str = "") -> None:
            try:
                lf.score(
                    trace_id=trace.id,
                    name=name,
                    value=value,
                    comment=comment if comment else None,
                )
            except Exception as exc:
                print(f" [warn] score({name}): {exc}")

        # ── assertions ──
        checks = run_assertions(row["final_answer"], row.get("retrieved_chunk_ids", []))
        all_pass = all(c.passed for c in checks)
        _score("all_assertions_pass", 1.0 if all_pass else 0.0)
        for c in checks:
            _score(c.name, 1.0 if c.passed else 0.0, c.detail)

        # ── judge ──
        if idx > 1:
            time.sleep(3)  # pace Groq RPM limit

        for version in judge_versions:
            try:
                from evaluation.judge import judge_response
                verdict = judge_response(
                    row["question"],
                    row["final_answer"],
                    row.get("retrieved_chunks", []),
                    version=version,
                )
            except Exception as exc:
                verdict = f"ERROR:{exc}"
            _score(f"judge_{version}", 1.0 if verdict == "GOOD" else 0.0, verdict)
            combined = all_pass and verdict == "GOOD"
            _score(f"overall_pass_{version}", 1.0 if combined else 0.0)

        # ── human label ──
        human = label_map.get(cid)
        if human:
            _score("human_label", 1.0 if human == "GOOD" else 0.0, human)

        # ── RAGAS (if available) ──
        ragas = ragas_map.get(cid, {})
        if ragas.get("ragas_faithfulness") is not None:
            _score("ragas_faithfulness", float(ragas["ragas_faithfulness"]))
        if ragas.get("ragas_answer_relevancy") is not None:
            _score("ragas_answer_relevancy", float(ragas["ragas_answer_relevancy"]))

        print(" done")

    lf.flush()
    print(f"\n  Experiment '{run_name}' complete.")
    print(f"  In Langfuse: Datasets > {_DATASET_NAME} > Runs")


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run billing-support eval as a Langfuse Dataset Experiment"
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Name for this experiment run (default: auto-generated from judge version)",
    )
    parser.add_argument(
        "--judge-version",
        default="v2",
        choices=["v1", "v2"],
        help="Judge prompt version to use (default: v2).",
    )
    parser.add_argument(
        "--all-judges",
        dest="all_judges",
        action="store_true",
        help="Run both v1 and v2 judges.",
    )
    parser.add_argument(
        "--setup-only",
        dest="setup_only",
        action="store_true",
        help="Only create/update the dataset items, do not run an experiment.",
    )
    args = parser.parse_args()

    # ── Langfuse client ──
    from src.generation.langfuse_client import get_langfuse
    lf = get_langfuse()
    if lf is None:
        print(
            "ERROR: Langfuse is not configured.\n"
            "       Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env and re-run."
        )
        sys.exit(1)

    # ── load data ──
    if not _ANSWERS.exists():
        print(f"ERROR: {_ANSWERS} not found. Run run_eval.py first.")
        sys.exit(1)

    answers = _load_jsonl(_ANSWERS)
    labels = _load_json(_LABELS) if _LABELS.exists() else []
    ragas_data = _load_json(_RAGAS) if _RAGAS.exists() else []
    ragas_map = {r["case_id"]: r for r in ragas_data}

    if not labels:
        print("[WARN] labels_25.json not found -- human_label scores will be skipped.")

    if ragas_map:
        print(f"[INFO] RAGAS scores found for {len(ragas_map)} cases -- will be included.")

    # ── ensure dataset exists ──
    print(f"\nSetting up dataset '{_DATASET_NAME}'...")
    ensure_dataset(lf, labels)
    lf.flush()

    if args.setup_only:
        print("\nDataset setup complete. Re-run without --setup-only to run an experiment.")
        return

    # ── determine judge versions and run name ──
    judge_versions = ["v1", "v2"] if args.all_judges else [args.judge_version]
    run_name = args.run_name or f"week6-{'_'.join(judge_versions)}-eval"

    run_experiment(lf, answers, labels, judge_versions, run_name, ragas_map)

    print("\nDone. Open Langfuse:")
    print(f"  Datasets > {_DATASET_NAME} > Runs tab  (see '{run_name}')")
    print("  Click any item to compare expected vs actual label + all scores")


if __name__ == "__main__":
    main()

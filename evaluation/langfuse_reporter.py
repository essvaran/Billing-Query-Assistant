"""Push evaluation results to Langfuse for dashboard visualisation.

Creates one Langfuse trace per eval case (grouped in a session) and logs:

  Scores per case:
    judge_v1 / judge_v2          1 = GOOD, 0 = NOT_GOOD
    human_label                  1 = GOOD, 0 = NOT_GOOD  (from labels_25.json)
    all_assertions_pass          1 or 0
    no_bare_article_id           1 or 0
    no_en_dash_in_citation       1 or 0
    no_hallucinated_error_code   1 or 0
    no_fabricated_citation       1 or 0
    overall_pass_<version>       1 if assertions AND that judge both pass
    ragas_faithfulness           0..1  (only if ragas_eval.py has been run)
    ragas_answer_relevancy       0..1  (only if ragas_eval.py has been run)

Usage (called from run_eval.py --push-langfuse):
    from evaluation.langfuse_reporter import push_eval_results
    push_eval_results(results)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_LABELS_PATH = Path(__file__).resolve().parent / "labels_25.json"


def push_eval_results(
    results: list,
    judge_versions: list[str] | None = None,
) -> None:
    """Upload results to Langfuse. No-op (with message) if Langfuse is not configured."""
    from src.generation.langfuse_client import get_langfuse

    lf = get_langfuse()
    if lf is None:
        print(
            "\n[Langfuse] Not configured -- skipping upload.\n"
            "           Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY in .env to enable."
        )
        return

    # Load human labels (optional)
    label_map: dict[str, str] = {}
    if _LABELS_PATH.exists():
        raw = json.loads(_LABELS_PATH.read_text(encoding="utf-8"))
        label_map = {row["case_id"]: row["label"] for row in raw}

    # Determine which judge versions have results in this batch
    if judge_versions is None:
        judge_versions = [v for v in ("v1", "v2") if any(f"judge_{v}" in r for r in results)]

    session_id = f"eval-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    uploaded = 0
    failed = 0

    print(f"\n[Langfuse] Uploading {len(results)} eval cases  (session={session_id})...")

    for row in results:
        try:
            trace = lf.trace(
                name="billing_eval_case",
                session_id=session_id,
                input={"question": row["question"]},
                output={"final_answer": row["final_answer"]},
                tags=[row.get("mode", ""), row["case_id"]],
                metadata={
                    "case_id": row["case_id"],
                    "mode": row.get("mode", ""),
                    "expected_behavior": row.get("expected_behavior", ""),
                    "is_regression": row.get("is_regression", False),
                    "retrieval_ms": row.get("retrieval_ms", 0),
                    "generation_ms": row.get("generation_ms", 0),
                    "retrieved_chunk_ids": row.get("retrieved_chunk_ids", []),
                },
            )

            def _score(name: str, value: float, comment: str = "") -> None:
                try:
                    lf.score(
                        trace_id=trace.id,
                        name=name,
                        value=value,
                        comment=comment if comment else None,
                    )
                except Exception as exc:
                    print(f"  [warn] score('{name}') on {row['case_id']}: {exc}")

            # --- Judge verdicts ---
            for v in judge_versions:
                verdict = row.get(f"judge_{v}")
                if verdict and not str(verdict).startswith("ERROR"):
                    _score(f"judge_{v}", 1.0 if verdict == "GOOD" else 0.0, verdict)

            # --- Human label ---
            human = label_map.get(row["case_id"])
            if human:
                _score("human_label", 1.0 if human == "GOOD" else 0.0, human)

            # --- Assertion scores ---
            assertions = row.get("assertions", {})
            _score("all_assertions_pass", 1.0 if row.get("all_assertions_pass") else 0.0)
            for aname, ares in assertions.items():
                _score(aname, 1.0 if ares.get("passed") else 0.0, ares.get("detail", ""))

            # --- Overall pass (assertions AND judge) ---
            for v in judge_versions:
                verdict = row.get(f"judge_{v}")
                if verdict and not str(verdict).startswith("ERROR"):
                    combined = bool(row.get("all_assertions_pass")) and (verdict == "GOOD")
                    _score(f"overall_pass_{v}", 1.0 if combined else 0.0)

            # --- RAGAS scores (optional) ---
            if row.get("ragas_faithfulness") is not None:
                _score("ragas_faithfulness", float(row["ragas_faithfulness"]))
            if row.get("ragas_answer_relevancy") is not None:
                _score("ragas_answer_relevancy", float(row["ragas_answer_relevancy"]))

            uploaded += 1

        except Exception as exc:
            print(f"  [warn] Failed to upload case {row.get('case_id', '?')}: {exc}")
            failed += 1

    try:
        lf.flush()
    except Exception:
        pass

    print(
        f"[Langfuse] Done. {uploaded} cases uploaded"
        + (f", {failed} failed" if failed else "")
        + f"  --  session '{session_id}'"
    )
    scores_logged = (
        ["judge_v1/v2" if judge_versions else ""]
        + (["human_label"] if label_map else [])
        + ["all_assertions_pass", "assertion checks", "overall_pass_v1/v2"]
        + (["ragas_faithfulness", "ragas_answer_relevancy"] if any(r.get("ragas_faithfulness") is not None for r in results) else [])
    )
    print(f"           Scores: {', '.join(s for s in scores_logged if s)}")
    print("           Open Langfuse > Sessions to find this run, or Scores for distributions.")

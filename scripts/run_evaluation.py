import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.bootstrap import ensure_project_root_on_path

ensure_project_root_on_path()

from src.evaluation.evaluate_retrieval import evaluate
from src.evaluation.export_results import export_evaluation_json


def main() -> None:
    evaluation = evaluate()
    export_evaluation_json(evaluation)

    print(f"Baseline Hit@5:        {evaluation['summary']['baseline_hit_at_5']}")
    print(f"Structure-aware Hit@5: {evaluation['summary']['structure_aware_hit_at_5']}")
    print(f"Semantic Hit@5:        {evaluation['summary']['semantic_hit_at_5']}")

    for row in evaluation["per_question"]:
        print(
            f"{row['question_id']}: baseline_rank={row['baseline_rank']} "
            f"structure_rank={row['structure_rank']} "
            f"semantic_rank={row['semantic_rank']}"
        )


if __name__ == "__main__":
    main()

import json

from src.config import EVALUATION_DIR


def export_evaluation_json(evaluation: dict, filename: str = "hit_at_5_results.json") -> None:
    output_path = EVALUATION_DIR / filename
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(evaluation, f, indent=2)
    print(f"Wrote evaluation results to {output_path}")

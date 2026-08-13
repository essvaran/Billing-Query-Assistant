import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.bootstrap import ensure_project_root_on_path

ensure_project_root_on_path()

from src.config import BASELINE_COLLECTION, EVALUATION_DIR, SEMANTIC_COLLECTION, STRUCTURE_AWARE_COLLECTION
from src.retrieval.search import search


def run_dump(collection_name: str, output_filename: str) -> None:
    with open(EVALUATION_DIR / "questions.json", encoding="utf-8") as f:
        questions = json.load(f)

    dump = []
    for question in questions:
        results = search(collection_name, question["question"])
        dump.append(
            {
                "question_id": question["id"],
                "question": question["question"],
                "results": results,
            }
        )

    output_path = EVALUATION_DIR / output_filename
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dump, f, indent=2)

    print(f"Wrote {len(dump)} question results to {output_path}")


def main() -> None:
    run_dump(BASELINE_COLLECTION, "baseline_search_dump.json")
    run_dump(STRUCTURE_AWARE_COLLECTION, "structure_search_dump.json")
    run_dump(SEMANTIC_COLLECTION, "semantic_search_dump.json")


if __name__ == "__main__":
    main()

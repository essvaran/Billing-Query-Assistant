import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.bootstrap import ensure_project_root_on_path

ensure_project_root_on_path()

from src.config import EVALUATION_DIR, STRUCTURE_AWARE_COLLECTION
from src.retrieval.filters import compare_filtered_vs_unfiltered

CANDIDATE_QUERIES = [
    "Who can view migration status?",
    "What roles are involved in migration?",
    "Can I keep using the old format going forward?",
    "What happens to a role during migration?",
]


def main() -> None:
    chosen = None

    for query in CANDIDATE_QUERIES:
        comparison = compare_filtered_vs_unfiltered(
            STRUCTURE_AWARE_COLLECTION, query, "billing-migration"
        )
        print(f"Query: {query!r} -> top1_changed={comparison['top1_changed']}")

        if comparison["top1_changed"] and chosen is None:
            chosen = comparison

    if chosen is None:
        raise RuntimeError("No candidate query produced a top-1 change; add more candidates.")

    output_path = EVALUATION_DIR / "filter_comparison.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chosen, f, indent=2)

    print(f"Wrote filter comparison to {output_path}")


if __name__ == "__main__":
    main()

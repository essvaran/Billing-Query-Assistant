import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.bootstrap import ensure_project_root_on_path

ensure_project_root_on_path()

from src.config import (
    BASELINE_COLLECTION,
    SEMANTIC_COLLECTION,
    STRUCTURE_AWARE_COLLECTION,
)
from src.catalog import settings
from src.generation.answer import answer_question
from src.generation.llm_client import LLMRequestError
from src.retrieval.search import search
from src.retrieval.vector_store import get_embeddings

_STRATEGIES = {
    "baseline": BASELINE_COLLECTION,
    "structure": STRUCTURE_AWARE_COLLECTION,
    "semantic": SEMANTIC_COLLECTION,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Billing Migration Help-Centre Assistant")
    parser.add_argument(
        "--strategy",
        choices=_STRATEGIES.keys(),
        default="structure",
        help="Chunking strategy / collection to search (default: structure)",
    )
    parser.add_argument(
        "--filter-product-area",
        default=None,
        help="Optional metadata filter for product_area (for example: billing-migration)",
    )
    parser.add_argument(
        "--compare-filters",
        action="store_true",
        help="Show both unfiltered and filtered retrieval results for each question",
    )
    return parser


def _print_results(label: str, chunks: list[dict]) -> None:
    print(f"{label} top results:")
    for chunk in chunks[:3]:
        print(
            f"  - {chunk['chunk_id']} | score={chunk['score']} | product_area={chunk.get('product_area')}"
        )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    collection = _STRATEGIES[args.strategy]
    where = None if not args.filter_product_area else {"product_area": args.filter_product_area}

    print("Billing Migration Help-Centre Assistant")
    print(f"Strategy: {args.strategy}  |  Collection: {collection}")
    print("Loading embedding model...", end=" ", flush=True)
    get_embeddings()
    print("ready.\n")
    print("Ask a question about billing migration, or type 'exit' to quit.\n")

    while True:
        question = input("> ").strip()

        if question.lower() in {"exit", "quit"}:
            break
        if not question:
            continue

        try:
            result = answer_question(question, collection_name=collection, where=where)
        except LLMRequestError as exc:
            print(f"\n[error] {exc}\n")
            continue

        if args.compare_filters and where is not None:
            unfiltered = search(collection, question, k=settings.get("docs.top_k"))
            filtered = search(collection, question, k=settings.get("docs.top_k"), where=where)
            print()
            _print_results("Unfiltered", unfiltered)
            _print_results("Filtered", filtered)
            print()

        print()
        print(result.final_answer)

        if result.raw_answer != result.final_answer:
            print(f"\n[debug] Raw LLM answer (before citation check):\n{result.raw_answer}")

        if result.citations_valid:
            print(f"\nCited chunks: {', '.join(sorted(result.citations))}")
        else:
            print(f"\n[debug] Citations found: {result.citations or 'none'} (valid={result.citations_valid})")

        total_ms = result.retrieval_ms + result.generation_ms
        print(
            f"\nTimings  —  retrieval: {result.retrieval_ms:.0f} ms  |  "
            f"generation: {result.generation_ms:.0f} ms  |  "
            f"total: {total_ms:.0f} ms"
        )

        print(f"\nRetrieved (top {len(result.retrieved_chunks)}):")
        for chunk in result.retrieved_chunks:
            print(f"  - {chunk['chunk_id']} (score {chunk['score']})")
        print()


if __name__ == "__main__":
    main()

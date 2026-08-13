import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.bootstrap import ensure_project_root_on_path

ensure_project_root_on_path()

from src.chunking.baseline import baseline_chunk_articles
from src.chunking.semantic import semantic_chunk_articles
from src.chunking.structure_aware import structure_aware_chunk_articles
from src.config import (
    ARTICLES_DIR,
    BASELINE_COLLECTION,
    SEMANTIC_COLLECTION,
    STRUCTURE_AWARE_COLLECTION,
)
from src.ingestion.loader import load_articles
from src.retrieval.vector_store import build_collection


def main() -> None:
    articles = load_articles(ARTICLES_DIR)
    print(f"Loaded articles: {len(articles)}")
    print(f"Metadata validation passed: {len(articles)}/{len(articles)}")

    baseline_chunks = baseline_chunk_articles(articles)
    structure_chunks = structure_aware_chunk_articles(articles)
    semantic_chunks = semantic_chunk_articles(articles)

    print(f"Baseline chunk count:        {len(baseline_chunks)}")
    print(f"Structure-aware chunk count: {len(structure_chunks)}")
    print(f"Semantic chunk count:        {len(semantic_chunks)}")

    build_collection(BASELINE_COLLECTION, baseline_chunks)
    build_collection(STRUCTURE_AWARE_COLLECTION, structure_chunks)
    build_collection(SEMANTIC_COLLECTION, semantic_chunks)

    print(f"Built collection: {BASELINE_COLLECTION}")
    print(f"Built collection: {STRUCTURE_AWARE_COLLECTION}")
    print(f"Built collection: {SEMANTIC_COLLECTION}")


if __name__ == "__main__":
    main()

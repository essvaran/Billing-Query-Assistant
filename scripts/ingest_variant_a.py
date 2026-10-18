"""Ingest the synthetic Variant A corpus into the Tier-1 collection.

Uses the existing structure-aware chunker unchanged (Week 12 rule: no chunker
rebuilds). Front-matter fields (slug, doc_type, policy_version, applies_to,
synthetic) flow into every chunk's metadata and are filterable at query time.

Run:  python scripts/ingest_variant_a.py
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.chunking.structure_aware import structure_aware_chunk_articles
from src.config import TIER1_COLLECTION, VARIANT_A_CORPUS_DIR
from src.ingestion.loader import load_articles
from src.retrieval.vector_store import build_collection


def main() -> None:
    if not VARIANT_A_CORPUS_DIR.exists():
        raise SystemExit("Corpus missing. Run: python scripts/generate_synthetic_corpus.py")

    articles = load_articles(VARIANT_A_CORPUS_DIR)
    chunks = structure_aware_chunk_articles(articles)
    by_type = Counter(c.metadata.get("doc_type", "?") for c in chunks)
    by_policy = Counter(c.metadata.get("policy_version", "?") for c in chunks)
    print(f"Loaded documents: {len(articles)}")
    print(f"Chunks: {len(chunks)}  by doc_type: {dict(by_type)}")
    print(f"Chunks by policy_version: {dict(by_policy)}")

    build_collection(TIER1_COLLECTION, chunks)
    print(f"Built collection: {TIER1_COLLECTION}")


if __name__ == "__main__":
    main()

import re

from rank_bm25 import BM25Okapi

from src.retrieval.vector_store import get_collection

_bm25_cache: dict[str, tuple[BM25Okapi, list[dict]]] = {}

# Keep letters, digits, and hyphens. Hyphens matter because error codes
# like "ERR-4040" must survive tokenization intact so they match across
# query and corpus. Everything else (?, |, ., comma, …) becomes a space.
_NON_TOKEN = re.compile(r"[^\w\-]")


def _tokenize(text: str) -> list[str]:
    return [t for t in _NON_TOKEN.sub(" ", text.lower()).split() if t]


def build_bm25_index(collection_name: str) -> tuple[BM25Okapi, list[dict]]:
    """Load all chunks from a ChromaDB collection and build a BM25 index."""
    collection = get_collection(collection_name)
    result = collection.get(include=["documents", "metadatas"])

    chunks = []
    for chunk_id, doc, meta in zip(result["ids"], result["documents"], result["metadatas"]):
        chunks.append(
            {
                "chunk_id": chunk_id,
                "text": doc,
                "article_id": meta.get("article_id"),
                "source_file": meta.get("source_file"),
                "section": meta.get("section"),
                "product_area": meta.get("product_area"),
            }
        )

    tokenized_corpus = [_tokenize(c["text"]) for c in chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    return bm25, chunks


def get_bm25_index(collection_name: str) -> tuple[BM25Okapi, list[dict]]:
    """Return a cached BM25 index, building it if necessary."""
    if collection_name not in _bm25_cache:
        _bm25_cache[collection_name] = build_bm25_index(collection_name)
    return _bm25_cache[collection_name]


def bm25_search(collection_name: str, query: str, k: int = 25) -> list[dict]:
    """Return top-k chunks by BM25 score."""
    bm25, chunks = get_bm25_index(collection_name)
    scores = bm25.get_scores(_tokenize(query))

    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]

    hits = []
    for rank, idx in enumerate(top_indices, start=1):
        hits.append(
            {
                "rank": rank,
                "chunk_id": chunks[idx]["chunk_id"],
                "article_id": chunks[idx]["article_id"],
                "source_file": chunks[idx]["source_file"],
                "section": chunks[idx]["section"],
                "product_area": chunks[idx]["product_area"],
                "bm25_score": round(float(scores[idx]), 4),
                "text": chunks[idx]["text"],
            }
        )
    return hits

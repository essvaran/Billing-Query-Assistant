from src.retrieval.bm25_search import bm25_search
from src.retrieval.search import search


def rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)


def hybrid_search(
    collection_name: str,
    query: str,
    dense_k: int = 25,
    bm25_k: int = 25,
    rrf_k: int = 60,
    top_n: int = 3,
    where: dict | None = None,
) -> list[dict]:
    """
    Fuse dense and BM25 ranked lists with Reciprocal Rank Fusion.

    RRF fuses RANKS, not scores — this avoids the scale mismatch between
    cosine similarity (0–1) and BM25 scores (0–N).

    rrf_k=60 is the value from the original Cormack et al. (2009) paper.
    """
    dense_hits = search(collection_name, query, k=dense_k, where=where)
    bm25_hits = bm25_search(collection_name, query, k=bm25_k, where=where)

    # accumulate RRF scores keyed by chunk_id
    rrf_scores: dict[str, float] = {}
    for hit in dense_hits:
        cid = hit["chunk_id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + rrf_score(hit["rank"], rrf_k)
    for hit in bm25_hits:
        cid = hit["chunk_id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + rrf_score(hit["rank"], rrf_k)

    # build a lookup for chunk metadata from both result sets
    chunk_meta: dict[str, dict] = {}
    for hit in dense_hits + bm25_hits:
        cid = hit["chunk_id"]
        if cid not in chunk_meta:
            chunk_meta[cid] = hit

    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_n]

    results = []
    for rank, (cid, score) in enumerate(ranked, start=1):
        meta = chunk_meta.get(cid, {})
        results.append(
            {
                "rank": rank,
                "chunk_id": cid,
                "article_id": meta.get("article_id"),
                "source_file": meta.get("source_file"),
                "section": meta.get("section"),
                "product_area": meta.get("product_area"),
                "slug": meta.get("slug"),
                "doc_type": meta.get("doc_type"),
                "policy_version": meta.get("policy_version"),
                "applies_to": meta.get("applies_to"),
                "last_updated": meta.get("last_updated"),
                "rrf_score": round(score, 6),
                "text": meta.get("text", ""),
            }
        )
    return results

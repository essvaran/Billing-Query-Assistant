from functools import lru_cache

import numpy as np

from src.retrieval.vector_store import get_collection, get_embeddings


@lru_cache(maxsize=8)
def _corpus_centroid(collection_name: str) -> np.ndarray:
    """Compute and cache the L2-normalised mean embedding of all chunks.

    Called once per collection per process lifetime. ChromaDB returns stored
    embeddings directly so no re-embedding is needed.
    """
    collection = get_collection(collection_name)
    result = collection.get(include=["embeddings"])
    vecs = np.array(result["embeddings"], dtype=np.float32)
    centroid = vecs.mean(axis=0)
    norm = np.linalg.norm(centroid)
    return centroid / norm if norm > 0 else centroid


def is_query_relevant(query: str, collection_name: str, threshold: float) -> bool:
    """Return True when the query is likely answerable from the corpus.

    Embeds the query and computes its cosine similarity against the corpus
    centroid.  Returns False (skip retrieval) when the similarity falls below
    the threshold, meaning the query topic is far from the indexed content.
    """
    embeddings = get_embeddings()
    query_vec = np.array(embeddings.embed_query(query), dtype=np.float32)
    norm = np.linalg.norm(query_vec)
    if norm > 0:
        query_vec = query_vec / norm

    centroid = _corpus_centroid(collection_name)
    similarity = float(np.dot(query_vec, centroid))
    return similarity >= threshold

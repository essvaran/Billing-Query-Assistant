from src.retrieval.vector_store import get_collection, get_embeddings


def search(collection_name: str, query: str, k: int | None = None, where: dict | None = None) -> list[dict]:
    if k is None:
        from src.catalog import settings
        k = settings.get("docs.top_k")
    from src.retrieval.filters import to_chroma_where

    collection = get_collection(collection_name)
    embeddings = get_embeddings()
    query_vector = embeddings.embed_query(query)
    where = to_chroma_where(where)

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=k,
        where=where,
    )

    hits = []
    ids = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for rank, (chunk_id, document, metadata, distance) in enumerate(
        zip(ids, documents, metadatas, distances), start=1
    ):
        similarity = 1 - distance
        hits.append(
            {
                "rank": rank,
                "chunk_id": chunk_id,
                "article_id": metadata.get("article_id"),
                "source_file": metadata.get("source_file"),
                "section": metadata.get("section"),
                "product_area": metadata.get("product_area"),
                "slug": metadata.get("slug"),
                "doc_type": metadata.get("doc_type"),
                "policy_version": metadata.get("policy_version"),
                "applies_to": metadata.get("applies_to"),
                "last_updated": metadata.get("last_updated"),
                "score": round(similarity, 4),
                "text": document,
            }
        )

    return hits

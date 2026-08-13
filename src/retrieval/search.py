from src.config import TOP_K
from src.retrieval.vector_store import get_collection, get_embeddings


def search(collection_name: str, query: str, k: int = TOP_K, where: dict | None = None) -> list[dict]:
    collection = get_collection(collection_name)
    embeddings = get_embeddings()
    query_vector = embeddings.embed_query(query)

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
                "score": round(similarity, 4),
                "text": document,
            }
        )

    return hits

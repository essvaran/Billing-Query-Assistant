import chromadb
from langchain_huggingface import HuggingFaceEmbeddings

from src.chunking.chunk_types import Chunk
from src.config import CHROMA_DB_DIR, EMBEDDING_MODEL

_embeddings = None


def get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embeddings


def get_client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=str(CHROMA_DB_DIR))


def build_collection(collection_name: str, chunks: list[Chunk]) -> None:
    client = get_client()
    client.delete_collection(collection_name) if collection_name in [
        c.name for c in client.list_collections()
    ] else None

    collection = client.create_collection(
        collection_name, metadata={"hnsw:space": "cosine"}
    )
    embeddings = get_embeddings()

    texts = [chunk.page_content for chunk in chunks]
    vectors = embeddings.embed_documents(texts)

    collection.add(
        ids=[chunk.metadata["chunk_id"] for chunk in chunks],
        embeddings=vectors,
        documents=texts,
        metadatas=[chunk.metadata for chunk in chunks],
    )


def get_collection(collection_name: str):
    client = get_client()
    return client.get_collection(collection_name)

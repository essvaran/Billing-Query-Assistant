import re

import numpy as np

from src.chunking.chunk_ids import make_chunk_id
from src.chunking.chunk_types import Chunk
from src.ingestion.loader import Article
from src.retrieval.vector_store import get_embeddings

# Rolling window: embed each sentence in the context of its neighbours,
# which gives more stable similarity signals than single-sentence embeddings.
_WINDOW_SIZE = 3

# Split where the inter-sentence distance is in the top PERCENTILE_THRESHOLD%.
# Lower = fewer, larger chunks. Higher = more, smaller chunks.
PERCENTILE_THRESHOLD = 95

_SENT_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")


def _split_sentences(text: str) -> list[str]:
    parts = _SENT_RE.split(text)
    return [p.strip() for p in parts if len(p.strip()) > 15]


def _windowed_texts(sentences: list[str]) -> list[str]:
    result = []
    half = _WINDOW_SIZE // 2
    for i in range(len(sentences)):
        start = max(0, i - half)
        end = min(len(sentences), i + half + 1)
        result.append(" ".join(sentences[start:end]))
    return result


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(1 - np.dot(a, b) / denom) if denom else 1.0


def _make_chunk(
    sentences: list[str], article: Article, index: int
) -> Chunk:
    chunk_id = make_chunk_id(
        article.metadata["article_id"], "semantic", f"{index:04d}"
    )
    return Chunk(
        page_content=" ".join(sentences),
        metadata={
            **article.metadata,
            "chunk_id": chunk_id,
            "chunk_index": index,
            "chunking_strategy": "semantic",
        },
    )


def semantic_chunk_article(article: Article) -> list[Chunk]:
    sentences = _split_sentences(article.content)

    if len(sentences) <= 1:
        return [_make_chunk([article.content.strip()], article, 1)]

    embeddings = get_embeddings()
    vectors = np.array(embeddings.embed_documents(_windowed_texts(sentences)))

    distances = [
        _cosine_distance(vectors[i], vectors[i + 1])
        for i in range(len(vectors) - 1)
    ]

    threshold = float(np.percentile(distances, PERCENTILE_THRESHOLD))
    breakpoints = {i + 1 for i, d in enumerate(distances) if d >= threshold}

    chunks: list[Chunk] = []
    current: list[str] = []

    for i, sentence in enumerate(sentences):
        if i in breakpoints and current:
            chunks.append(_make_chunk(current, article, len(chunks) + 1))
            current = []
        current.append(sentence)

    if current:
        chunks.append(_make_chunk(current, article, len(chunks) + 1))

    return chunks


def semantic_chunk_articles(articles: list[Article]) -> list[Chunk]:
    chunks = []
    for article in articles:
        chunks.extend(semantic_chunk_article(article))
    return chunks

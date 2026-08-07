from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.chunking.chunk_ids import make_chunk_id
from src.chunking.chunk_types import Chunk
from src.config import BASELINE_CHUNK_OVERLAP, BASELINE_CHUNK_SIZE
from src.ingestion.loader import Article

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=BASELINE_CHUNK_SIZE,
    chunk_overlap=BASELINE_CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def baseline_chunk_article(article: Article) -> list[Chunk]:
    text_pieces = _splitter.split_text(article.content)
    chunks = []

    for index, text_piece in enumerate(text_pieces, start=1):
        chunk_id = make_chunk_id(
            article.metadata["article_id"], "baseline", f"{index:04d}"
        )
        metadata = {
            **article.metadata,
            "chunk_id": chunk_id,
            "chunk_index": index,
            "chunking_strategy": "baseline",
        }
        chunks.append(Chunk(page_content=text_piece, metadata=metadata))

    return chunks


def baseline_chunk_articles(articles: list[Article]) -> list[Chunk]:
    chunks = []
    for article in articles:
        chunks.extend(baseline_chunk_article(article))
    return chunks

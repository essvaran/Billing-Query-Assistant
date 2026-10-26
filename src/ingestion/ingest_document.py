from pathlib import Path

from src.chunking.baseline import baseline_chunk_article
from src.chunking.structure_aware import structure_aware_chunk_article
from src.config import DEFAULT_COLLECTION
from src.ingestion.loader import load_article
from src.retrieval.vector_store import add_chunks_to_collection

SUPPORTED_EXTENSIONS = {".pdf", ".md", ".txt", ".docx", ".xlsx", ".xls"}


def ingest_file(file_path: Path, collection_name: str = DEFAULT_COLLECTION) -> int:
    """Load, chunk, and index a single file into an existing collection.

    Uses structure-aware chunking when the file has Markdown ## headings;
    falls back to baseline chunking otherwise (e.g. plain PDFs / DOCX).

    Returns the number of chunks indexed.
    """
    article = load_article(file_path)
    if not article.content.strip():
        raise ValueError(
            "No text could be extracted (scanned/image-only PDFs are not supported without OCR)."
        )
    chunks = structure_aware_chunk_article(article)
    if not chunks:
        chunks = baseline_chunk_article(article)
    return add_chunks_to_collection(collection_name, chunks)

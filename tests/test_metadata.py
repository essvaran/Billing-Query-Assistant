import pytest

from src.chunking.baseline import baseline_chunk_articles
from src.chunking.structure_aware import structure_aware_chunk_articles
from src.ingestion.loader import load_article, load_articles
from src.ingestion.metadata import validate_metadata

REQUIRED_CHUNK_FIELDS = {
    "source_file",
    "article_id",
    "product_area",
    "last_updated",
    "chunk_id",
}


def test_all_six_articles_load():
    articles = load_articles()
    assert len(articles) == 6


def test_missing_metadata_raises():
    with pytest.raises(ValueError):
        validate_metadata({"source_file": "x.md", "article_id": "HC-1"})


def test_baseline_chunks_have_required_metadata():
    articles = load_articles()
    chunks = baseline_chunk_articles(articles)

    assert chunks
    for chunk in chunks:
        assert REQUIRED_CHUNK_FIELDS.issubset(chunk.metadata.keys())


def test_structure_aware_chunks_have_required_metadata():
    articles = load_articles()
    chunks = structure_aware_chunk_articles(articles)

    assert chunks
    for chunk in chunks:
        assert REQUIRED_CHUNK_FIELDS.issubset(chunk.metadata.keys())


def test_load_article_supports_plain_text_without_front_matter(tmp_path):
    file_path = tmp_path / "notes.txt"
    file_path.write_text("Plain text content", encoding="utf-8")

    article = load_article(file_path)

    assert article.content == "Plain text content"
    assert article.metadata["source_file"] == file_path.name
    assert article.metadata["article_id"] == "notes"
    assert article.metadata["product_area"] == "unknown"

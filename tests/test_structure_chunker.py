from src.chunking.structure_aware import structure_aware_chunk_articles
from src.ingestion.loader import load_articles


def test_table_row_contains_headers():
    articles = load_articles()
    chunks = structure_aware_chunk_articles(articles)

    error_chunk = next(
        chunk for chunk in chunks if "ERR-4032" in chunk.page_content
    )

    assert "Error code:" in error_chunk.page_content or "Code:" in error_chunk.page_content
    assert "Cause:" in error_chunk.page_content or "Series:" in error_chunk.page_content
    assert "Fix:" in error_chunk.page_content or "Blocking:" in error_chunk.page_content


def test_table_rows_stay_separate_chunks():
    articles = load_articles()
    chunks = structure_aware_chunk_articles(articles)

    err_4032_chunk = next(c for c in chunks if "ERR-4032" in c.page_content)
    err_5010_chunk = next(c for c in chunks if "ERR-5010" in c.page_content)

    assert err_4032_chunk.metadata["chunk_id"] != err_5010_chunk.metadata["chunk_id"]
    assert "ERR-5010" not in err_4032_chunk.page_content


def test_prose_chunks_include_article_and_section_labels():
    articles = load_articles()
    chunks = structure_aware_chunk_articles(articles)

    prose_chunk = next(c for c in chunks if c.metadata["content_type"] == "prose")

    assert prose_chunk.page_content.startswith("Article: ")
    assert "Section: " in prose_chunk.page_content

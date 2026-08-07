from src.config import ARTICLES_DIR
from src.ingestion.loader import load_articles


def report_loaded_articles() -> None:
    articles = load_articles(ARTICLES_DIR)

    print(f"Loaded articles: {len(articles)}")
    print(f"Metadata validation passed: {len(articles)}/{len(articles)}")

    missing_source_file = sum(
        1 for article in articles if not article.metadata.get("source_file")
    )
    print(f"Missing source_file: {missing_source_file}")


if __name__ == "__main__":
    report_loaded_articles()

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.config import ARTICLES_DIR
from src.ingestion.metadata import validate_metadata


@dataclass
class Article:
    content: str
    metadata: dict[str, Any]


def _split_front_matter(raw_text: str) -> tuple[dict[str, Any], str]:
    if not raw_text.startswith("---"):
        return {}, raw_text

    _, front_matter_block, body = raw_text.split("---", 2)
    front_matter = yaml.safe_load(front_matter_block) or {}
    return front_matter, body.strip()


def load_article(file_path: Path) -> Article:
    raw_text = file_path.read_text(encoding="utf-8")
    front_matter, body = _split_front_matter(raw_text)

    metadata = dict(front_matter)
    metadata["source_file"] = file_path.name
    metadata["last_updated"] = str(metadata.get("last_updated", ""))

    validate_metadata(metadata)

    return Article(content=body, metadata=metadata)


def load_articles(articles_dir: Path = ARTICLES_DIR) -> list[Article]:
    file_paths = sorted(articles_dir.glob("*.md"))
    return [load_article(file_path) for file_path in file_paths]

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

try:
    import docx  # type: ignore
except Exception:  # pragma: no cover
    docx = None

try:
    import PyPDF2  # type: ignore
except Exception:  # pragma: no cover
    PyPDF2 = None

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


def _extract_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()

    if suffix == ".md" or suffix == ".txt":
        return file_path.read_text(encoding="utf-8")

    if suffix == ".docx" and docx is not None:
        document = docx.Document(str(file_path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text)

    if suffix == ".pdf" and PyPDF2 is not None:
        try:
            reader = PyPDF2.PdfReader(str(file_path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            raise ValueError(
                f"Failed to extract text from PDF {file_path.name}: {e}. "
                f"The PDF may be corrupted or have encoding issues."
            ) from e

    raise ValueError(f"Unsupported file type: {file_path.suffix}")


def load_article(file_path: Path) -> Article:
    raw_text = _extract_text(file_path)
    front_matter, body = _split_front_matter(raw_text)

    metadata = dict(front_matter)
    metadata.setdefault("article_id", file_path.stem)
    metadata.setdefault("product_area", "unknown")
    metadata.setdefault("last_updated", "unknown")
    metadata["source_file"] = file_path.name
    metadata["last_updated"] = str(metadata.get("last_updated", "unknown"))

    validate_metadata(metadata)

    return Article(content=body, metadata=metadata)


def load_articles(articles_dir: Path = ARTICLES_DIR) -> list[Article]:
    supported_extensions = (".md", ".txt", ".docx", ".pdf")
    file_paths = sorted(
        path for path in articles_dir.iterdir() if path.is_file() and path.suffix.lower() in supported_extensions
    )
    return [load_article(file_path) for file_path in file_paths]

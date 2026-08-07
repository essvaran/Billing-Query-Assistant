import re


def slugify(text: str) -> str:
    slug = text.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def make_chunk_id(article_id: str, section: str, content_identifier: str) -> str:
    return f"{article_id}--{slugify(section)}--{content_identifier}"

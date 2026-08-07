import re

from src.chunking.chunk_ids import make_chunk_id, slugify
from src.chunking.chunk_types import Chunk
from src.ingestion.loader import Article

_SECTION_HEADING_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def _extract_title(content: str) -> str:
    match = _TITLE_RE.search(content)
    return match.group(1).strip() if match else ""


def _split_sections(content: str) -> list[tuple[str, str]]:
    headings = list(_SECTION_HEADING_RE.finditer(content))
    sections = []

    for index, heading_match in enumerate(headings):
        section_title = heading_match.group(1).strip()
        start = heading_match.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
        section_body = content[start:end].strip()
        sections.append((section_title, section_body))

    return sections


def _is_table_line(line: str) -> bool:
    return line.strip().startswith("|")


def _is_separator_line(line: str) -> bool:
    return bool(re.match(r"^\|?[\s:|-]+\|?$", line.strip()))


def _parse_table(table_lines: list[str]) -> tuple[list[str], list[list[str]]]:
    def parse_row(line: str) -> list[str]:
        cells = line.strip().strip("|").split("|")
        return [cell.strip() for cell in cells]

    header = parse_row(table_lines[0])
    data_rows = [
        parse_row(line)
        for line in table_lines[1:]
        if not _is_separator_line(line)
    ]
    return header, data_rows


def _split_blocks(section_body: str) -> list[str]:
    return [block for block in section_body.split("\n\n") if block.strip()]


def structure_aware_chunk_article(article: Article) -> list[Chunk]:
    title = _extract_title(article.content)
    sections = _split_sections(article.content)
    chunks = []

    for section_title, section_body in sections:
        prose_blocks = []
        table_row_index = 0
        prose_index = 0

        for block in _split_blocks(section_body):
            lines = [line for line in block.split("\n") if line.strip()]

            if lines and all(_is_table_line(line) for line in lines):
                header, data_rows = _parse_table(lines)

                for row in data_rows:
                    labelled_lines = [
                        f"{header_cell}: {cell}"
                        for header_cell, cell in zip(header, row)
                    ]
                    row_text = (
                        f"Article: {title}\n"
                        f"Section: {section_title}\n\n"
                        + "\n".join(labelled_lines)
                    )

                    identifier_source = row[0] if row else f"row-{table_row_index:03d}"
                    content_identifier = slugify(identifier_source) or f"row-{table_row_index:03d}"
                    table_row_index += 1

                    chunk_id = make_chunk_id(
                        article.metadata["article_id"], section_title, content_identifier
                    )
                    metadata = {
                        **article.metadata,
                        "chunk_id": chunk_id,
                        "section": section_title,
                        "content_type": "table_row",
                        "chunking_strategy": "structure_aware",
                    }
                    chunks.append(Chunk(page_content=row_text, metadata=metadata))
            else:
                prose_blocks.append(block)

        if prose_blocks:
            prose_index += 1
            prose_text = (
                f"Article: {title}\n"
                f"Section: {section_title}\n\n"
                + "\n\n".join(prose_blocks)
            )
            chunk_id = make_chunk_id(
                article.metadata["article_id"], section_title, f"prose-{prose_index:03d}"
            )
            metadata = {
                **article.metadata,
                "chunk_id": chunk_id,
                "section": section_title,
                "content_type": "prose",
                "chunking_strategy": "structure_aware",
            }
            chunks.append(Chunk(page_content=prose_text, metadata=metadata))

    return chunks


def structure_aware_chunk_articles(articles: list[Article]) -> list[Chunk]:
    chunks = []
    for article in articles:
        chunks.extend(structure_aware_chunk_article(article))
    return chunks

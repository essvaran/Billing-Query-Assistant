from src.catalog import prompts
from src.generation.refusal import refusal_message


def system_prompt() -> str:
    """The Docs-mode system prompt: catalog prompt docs.system with the current refusal message filled in."""
    return prompts.render("docs.system", refusal_message=refusal_message())


def prompt_version() -> str:
    """Recorded on every Docs trace; follows the active version of docs.system."""
    return f"v{prompts.active_version('docs.system')}"


def build_context(chunks: list[dict]) -> str:
    blocks = []
    for chunk in chunks:
        blocks.append(
            f"[Chunk ID: {chunk['chunk_id']}]\n"
            f"[Article ID: {chunk['article_id']}]\n"
            f"[Section: {chunk['section']}]\n\n"
            f"{chunk['text']}"
        )
    return "\n\n---\n\n".join(blocks)


def build_user_prompt(question: str, chunks: list[dict]) -> str:
    context = build_context(chunks)
    return f"Context:\n\n{context}\n\nQuestion: {question}"

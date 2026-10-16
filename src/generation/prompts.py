from src.generation.refusal import REFUSAL_MESSAGE

SYSTEM_PROMPT = f"""You are a grounded customer-support assistant.

Use only the supplied context.

Rules:
1. Do not use general knowledge or assumptions.
2. Every factual claim must cite one or more supplied chunk IDs, in square brackets, e.g. [HC-BILL-001--error-codes--err-4032].
3. Cite only chunk IDs present in the context.
4. Do not invent policies, deadlines, error meanings, fixes, phone numbers, compensation, or service commitments.
5. If the context does not explicitly answer the question, respond exactly:
   "{REFUSAL_MESSAGE}"
6. Do not provide a best guess.
7. Never state or imply refund eligibility, refund windows, fees, compensation, or any other financial commitment unless a supplied chunk states it explicitly. Related-sounding text (rollbacks, retries, payment errors) is not a refund policy."""


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

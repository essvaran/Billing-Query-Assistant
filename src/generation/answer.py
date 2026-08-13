import time
from dataclasses import dataclass, field

from src.config import STRUCTURE_AWARE_COLLECTION, TOP_K
from src.generation.citations import extract_citations, validate_citations
from src.generation.llm_client import ask_llm
from src.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from src.generation.refusal import REFUSAL_MESSAGE
from src.retrieval.search import search


@dataclass
class Answer:
    question: str
    retrieved_chunks: list[dict]
    raw_answer: str
    final_answer: str
    citations: set[str]
    citations_valid: bool
    retrieval_ms: float = field(default=0.0)
    generation_ms: float = field(default=0.0)


def answer_question(
    question: str,
    collection_name: str = STRUCTURE_AWARE_COLLECTION,
    k: int = TOP_K,
    where: dict | None = None,
) -> Answer:
    t0 = time.perf_counter()
    retrieved_chunks = search(collection_name, question, k=k, where=where)
    retrieval_ms = (time.perf_counter() - t0) * 1000

    retrieved_ids = {chunk["chunk_id"] for chunk in retrieved_chunks}

    if not retrieved_chunks:
        return Answer(
            question=question,
            retrieved_chunks=[],
            raw_answer=REFUSAL_MESSAGE,
            final_answer=REFUSAL_MESSAGE,
            citations=set(),
            citations_valid=False,
            retrieval_ms=retrieval_ms,
            generation_ms=0.0,
        )

    user_prompt = build_user_prompt(question, retrieved_chunks)

    t1 = time.perf_counter()
    raw_answer = ask_llm(SYSTEM_PROMPT, user_prompt)
    generation_ms = (time.perf_counter() - t1) * 1000

    if raw_answer.strip() == REFUSAL_MESSAGE:
        return Answer(
            question=question,
            retrieved_chunks=retrieved_chunks,
            raw_answer=raw_answer,
            final_answer=REFUSAL_MESSAGE,
            citations=set(),
            citations_valid=False,
            retrieval_ms=retrieval_ms,
            generation_ms=generation_ms,
        )

    citations = extract_citations(raw_answer)
    citations_valid = validate_citations(citations, retrieved_ids)

    final_answer = raw_answer if citations_valid else REFUSAL_MESSAGE

    return Answer(
        question=question,
        retrieved_chunks=retrieved_chunks,
        raw_answer=raw_answer,
        final_answer=final_answer,
        citations=citations,
        citations_valid=citations_valid,
        retrieval_ms=retrieval_ms,
        generation_ms=generation_ms,
    )

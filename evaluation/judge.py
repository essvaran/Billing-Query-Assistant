"""LLM-as-judge for Week 6 evaluation.

Loads the judge prompt from judge_v1.txt (or judge_v2.txt when available),
calls the configured LLM, and returns a binary GOOD / NOT_GOOD verdict.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.generation.llm_client import ask_llm

_EVAL_DIR = Path(__file__).resolve().parent


def _load_prompt(version: str) -> str:
    path = _EVAL_DIR / f"judge_{version}.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"Judge prompt not found: {path}. "
            f"Expected a file named judge_{version}.txt in evaluation/."
        )
    return path.read_text(encoding="utf-8").strip()


def judge_response(
    question: str,
    answer: str,
    retrieved_chunks: list,
    version: str = "v1",
) -> str:
    """Return 'GOOD' or 'NOT_GOOD'.

    Parameters
    ----------
    question:
        The original user question.
    answer:
        The final_answer string produced by answer_question().
    retrieved_chunks:
        List of chunk dicts with keys chunk_id and text.
    version:
        Which judge prompt file to load ('v1' or 'v2').
    """
    system_prompt = _load_prompt(version)

    context_parts = []
    for i, chunk in enumerate(retrieved_chunks[:5], 1):
        chunk_id = chunk.get("chunk_id", f"chunk-{i}")
        text = chunk.get("text", "")[:400]
        context_parts.append(f"[Chunk {i}: {chunk_id}]\n{text}")

    if context_parts:
        context_block = "\n\n".join(context_parts)
    else:
        context_block = "(no chunks retrieved — corpus gap or pre-retrieval gate fired)"

    user_msg = (
        f"Question: {question}\n\n"
        f"Context provided to the assistant:\n{context_block}\n\n"
        f"Assistant response:\n{answer}"
    )

    raw, _, _ = ask_llm(system_prompt, user_msg)
    upper = raw.strip().upper()
    if "NOT_GOOD" in upper or "NOT GOOD" in upper:
        return "NOT_GOOD"
    if "GOOD" in upper:
        return "GOOD"
    return "NOT_GOOD"

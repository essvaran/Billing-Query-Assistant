"""RAGAS-compatible metrics for the billing-support RAG system.

Implements the same two metrics as RAGAS, using our existing ask_llm instead
of the ragas library (which conflicts with newer langchain-community versions
via a removed ChatVertexAI import).

Metrics (no ground-truth answers required):
  faithfulness       -- fraction of answer claims supported by retrieved context
  answer_relevancy   -- how well the answer addresses the question (0..1)

Refusal cases ("I cannot answer ...") are skipped.

Usage
-----
    python evaluation/ragas_eval.py
    python evaluation/ragas_eval.py --input evaluation/answers_25.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

_EVAL_DIR = Path(__file__).resolve().parent
_REFUSAL = "I cannot answer that from the indexed help-centre articles."

# ── Faithfulness ──────────────────────────────────────────────────────────────
# Methodology (mirrors RAGAS):
#   1. Ask LLM to identify all distinct factual claims in the answer.
#   2. For each claim, ask LLM whether it is supported by the provided context.
#   3. Score = supported_claims / total_claims.

_CLAIM_EXTRACTION_SYSTEM = """\
You are an expert analyst. Given a question and an AI assistant's response,
list every distinct factual claim the response makes.

Output rules:
- One claim per line, no bullets or numbering.
- Each claim must be a complete, standalone statement.
- Omit meta-statements like "Based on the context..." or "According to...".
- If the response makes zero claims (e.g. it is a refusal), output exactly: NONE
"""

_CLAIM_VERDICT_SYSTEM = """\
You are an expert fact-checker. Given a set of context excerpts and a single
factual claim, decide whether the context DIRECTLY supports the claim.

Reply with exactly one word: SUPPORTED or NOT_SUPPORTED
"""


def _extract_claims(question: str, answer: str) -> list[str]:
    from src.generation.llm_client import ask_llm

    user_msg = f"Question: {question}\n\nAI response:\n{answer}\n\nList every distinct factual claim:"
    raw, _, _ = ask_llm(_CLAIM_EXTRACTION_SYSTEM, user_msg)
    lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]
    if not lines or lines[0].upper() == "NONE":
        return []
    return lines


def _check_claim(claim: str, context_text: str) -> bool:
    from src.generation.llm_client import ask_llm

    user_msg = f"Context:\n{context_text}\n\nClaim:\n{claim}\n\nIs this claim supported?"
    raw, _, _ = ask_llm(_CLAIM_VERDICT_SYSTEM, user_msg)
    return "NOT_SUPPORTED" not in raw.upper() and "SUPPORTED" in raw.upper()


def score_faithfulness(question: str, answer: str, chunks: list[dict]) -> float:
    """Return faithfulness score 0..1. Returns 1.0 for refusals (no claims made)."""
    if answer.strip() == _REFUSAL:
        return 1.0

    context_text = "\n\n".join(
        f"[{c.get('chunk_id', f'chunk-{i}')}]: {c.get('text', '')[:400]}"
        for i, c in enumerate(chunks[:5])
    )

    claims = _extract_claims(question, answer)
    if not claims:
        return 1.0

    supported = 0
    for claim in claims:
        time.sleep(2)  # pace Groq RPM limit
        if _check_claim(claim, context_text):
            supported += 1

    return round(supported / len(claims), 4)


# ── Answer Relevancy ─────────────────────────────────────────────────────────
# Methodology (mirrors RAGAS):
#   1. Ask LLM to generate n synthetic questions that the answer would address.
#   2. Embed those generated questions and the original question.
#   3. Score = mean cosine similarity(original_q, generated_q_i).

_QUESTION_GEN_SYSTEM = """\
You are an expert at inferring questions from answers.
Given a billing support AI response, generate 3 distinct questions that this
response would naturally answer.

Output rules:
- One question per line, no bullets or numbering.
- Questions must be specific, self-contained, and in a customer's voice.
- Do NOT repeat the same question with different wording.
"""


def _generate_questions(answer: str) -> list[str]:
    from src.generation.llm_client import ask_llm

    user_msg = f"AI response:\n{answer}\n\nGenerate 3 questions this response would answer:"
    raw, _, _ = ask_llm(_QUESTION_GEN_SYSTEM, user_msg)
    lines = [l.strip() for l in raw.strip().splitlines() if l.strip() and "?" in l]
    return lines[:3] if lines else []


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _embed(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts using the project's sentence-transformer model."""
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        vecs = model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vecs]
    except ImportError:
        raise ImportError(
            "sentence-transformers is required for answer_relevancy. "
            "Install: pip install sentence-transformers"
        )


def score_answer_relevancy(question: str, answer: str) -> float:
    """Return answer_relevancy score 0..1."""
    if answer.strip() == _REFUSAL:
        # A correct refusal is on-topic but not a direct answer.
        return 0.8

    generated_qs = _generate_questions(answer)
    if not generated_qs:
        return 0.0

    all_texts = [question] + generated_qs
    vecs = _embed(all_texts)
    q_vec = vecs[0]
    gen_vecs = vecs[1:]

    similarities = [_cosine_similarity(q_vec, gv) for gv in gen_vecs]
    return round(sum(similarities) / len(similarities), 4)


# ── runner ────────────────────────────────────────────────────────────────────

def run_ragas(answers: list) -> list:
    """Compute faithfulness and answer_relevancy for each answerable row."""
    eval_rows = [
        r for r in answers
        if r.get("retrieved_chunks")
    ]
    skipped = len(answers) - len(eval_rows)
    if skipped:
        print(f"  Skipping {skipped} cases with no retrieved chunks.")
    print(f"  Scoring {len(eval_rows)} cases...")

    for i, row in enumerate(eval_rows, 1):
        cid = row["case_id"]
        q = row["question"]
        a = row["final_answer"]
        chunks = row.get("retrieved_chunks", [])

        print(f"  [{i:2}/{len(eval_rows)}] {cid}: faithfulness...", end="", flush=True)
        try:
            faith = score_faithfulness(q, a, chunks)
        except Exception as exc:
            print(f" ERROR ({exc})")
            faith = None

        if faith is not None:
            print(f" {faith:.3f}  relevancy...", end="", flush=True)

        if i > 1:
            time.sleep(3)

        try:
            rel = score_answer_relevancy(q, a)
        except Exception as exc:
            print(f" ERROR ({exc})")
            rel = None

        if rel is not None:
            print(f" {rel:.3f}")

        row["ragas_faithfulness"] = faith
        row["ragas_answer_relevancy"] = rel

        if i < len(eval_rows):
            time.sleep(3)  # pace Groq RPM limit

    # Rows that were skipped get None
    scored_ids = {r["case_id"] for r in eval_rows}
    for row in answers:
        if row["case_id"] not in scored_ids:
            row.setdefault("ragas_faithfulness", None)
            row.setdefault("ragas_answer_relevancy", None)

    return answers


# ── reporting ─────────────────────────────────────────────────────────────────

def print_ragas_table(results: list) -> None:
    scored = [r for r in results if r.get("ragas_faithfulness") is not None]
    if not scored:
        print("\n[RAGAS] No cases scored.")
        return

    avg_faith = sum(r["ragas_faithfulness"] for r in scored) / len(scored)
    avg_rel = sum(r["ragas_answer_relevancy"] for r in scored if r.get("ragas_answer_relevancy") is not None) / len(scored)

    print(f"\n{'=' * 68}")
    print("RAGAS-COMPATIBLE METRICS")
    print("=" * 68)
    print(f"  {'Case':<6}  {'Mode':<26}  {'Faithfulness':>12}  {'Ans Relevancy':>13}")
    print("  " + "-" * 62)
    for r in scored:
        faith_str = f"{r['ragas_faithfulness']:.3f}" if r["ragas_faithfulness"] is not None else "  ERROR"
        rel_str = f"{r['ragas_answer_relevancy']:.3f}" if r.get("ragas_answer_relevancy") is not None else "  ERROR"
        print(f"  {r['case_id']:<6}  {r['mode']:<26}  {faith_str:>12}  {rel_str:>13}")
    print("  " + "-" * 62)
    print(f"  {'AVG':<34}  {avg_faith:>12.3f}  {avg_rel:>13.3f}")
    print(f"\n  n={len(scored)} cases scored  |  methodology: RAGAS faithfulness + answer_relevancy")


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="RAGAS-compatible evaluation for billing-support RAG"
    )
    parser.add_argument(
        "--input",
        default=str(_EVAL_DIR / "answers_25.jsonl"),
        help="Path to answers JSONL file (default: evaluation/answers_25.jsonl)",
    )
    parser.add_argument(
        "--output",
        default=str(_EVAL_DIR / "ragas_results.json"),
        help="Output path for results (default: evaluation/ragas_results.json)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: {input_path} not found. Run run_eval.py first.")
        sys.exit(1)

    print(f"Loading {input_path}...")
    with input_path.open(encoding="utf-8") as f:
        answers = [json.loads(line) for line in f if line.strip()]
    print(f"Loaded {len(answers)} cases.")

    answers = run_ragas(answers)
    print_ragas_table(answers)

    output_path = Path(args.output)
    output_path.write_text(
        json.dumps(answers, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nRAGAS results saved -> {output_path}")


if __name__ == "__main__":
    main()

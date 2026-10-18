import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.bootstrap import ensure_project_root_on_path

ensure_project_root_on_path()

from src.config import (
    BASELINE_COLLECTION,
    EVALUATION_DIR,
    PROJECT_ROOT,
    STRUCTURE_AWARE_COLLECTION,
)
from src.generation.answer import answer_question
from src.generation.llm_client import LLMRequestError

# Q1 = table error-code meaning, Q5 = procedure (prose), Q7 = role-permission table
ANSWERABLE_IDS = ["Q1", "Q5", "Q7"]

REFUSAL_QUESTIONS = [
    {
        "question": "What is the guaranteed refund SLA for billing migration issues?",
        "reason": "No refund SLA or guarantee period appears in the indexed articles.",
    },
    {
        "question": "What compensation is offered for service downtime during billing migration?",
        "reason": "No compensation policy or downtime commitment appears in the indexed articles.",
    },
    {
        "question": "What is the billing support phone number for emergency migration issues?",
        "reason": "No phone number or emergency contact information appears in the indexed articles.",
    },
]

# Q4 is the best bonus candidate: structure-aware retrieves the exact ERR-6030 row (rank 1)
# while baseline retrieves the full table (rank 3). The full table may carry more context.
BONUS_QUESTION = "How do I fix ERR-6030?"

RESULTS_MD = PROJECT_ROOT / "docs" / "archive" / "evaluation" / "results.md"


def _load_questions() -> dict:
    with open(EVALUATION_DIR / "questions.json", encoding="utf-8") as f:
        return {q["id"]: q for q in json.load(f)}


def _format_chunk_list(chunks: list[dict]) -> str:
    return "\n".join(
        f"{c['rank']}. `{c['chunk_id']}` — score {c['score']}"
        for c in chunks
    )


def run_answerable(questions: dict) -> list[dict]:
    records = []
    for qid in ANSWERABLE_IDS:
        q = questions[qid]
        print(f"  {qid}: {q['question']!r}")
        result = answer_question(q["question"])
        records.append(
            {
                "question_id": qid,
                "question": q["question"],
                "retrieved_chunks": result.retrieved_chunks,
                "answer": result.final_answer,
                "citations": sorted(result.citations),
                "citations_valid": result.citations_valid,
            }
        )
        status = "PASS" if result.citations_valid else "FAIL"
        print(f"    citations={sorted(result.citations)} [{status}]")
    return records


def run_refusals() -> list[dict]:
    records = []
    for i, item in enumerate(REFUSAL_QUESTIONS, start=1):
        print(f"  R{i}: {item['question']!r}")
        result = answer_question(item["question"])
        records.append(
            {
                "question_id": f"R{i}",
                "question": item["question"],
                "reason": item["reason"],
                "retrieved_chunks": result.retrieved_chunks,
                "answer": result.final_answer,
            }
        )
        print(f"    response={result.final_answer!r}")
    return records


def run_bonus() -> dict:
    print(f"  Bonus: {BONUS_QUESTION!r}")
    baseline = answer_question(BONUS_QUESTION, collection_name=BASELINE_COLLECTION)
    structure = answer_question(BONUS_QUESTION, collection_name=STRUCTURE_AWARE_COLLECTION)
    return {
        "question": BONUS_QUESTION,
        "baseline": {
            "top_chunk": baseline.retrieved_chunks[0] if baseline.retrieved_chunks else None,
            "answer": baseline.final_answer,
        },
        "structure_aware": {
            "top_chunk": structure.retrieved_chunks[0] if structure.retrieved_chunks else None,
            "answer": structure.final_answer,
        },
    }


def render_answerable_section(records: list[dict]) -> str:
    parts = []
    for i, r in enumerate(records, start=1):
        chunk_list = _format_chunk_list(r["retrieved_chunks"])
        citations = ", ".join(f"`{c}`" for c in r["citations"]) or "none"
        validity = "PASS" if r["citations_valid"] else "FAIL"
        parts.append(
            f"### Answerable Question {i} — {r['question_id']}\n\n"
            f"**Question:** {r['question']}\n\n"
            f"**Retrieved chunks (top {len(r['retrieved_chunks'])}):**\n\n"
            f"{chunk_list}\n\n"
            f"**Answer:**\n\n"
            f"> {r['answer']}\n\n"
            f"**Citations:** {citations}  \n"
            f"**Citation validation:** {validity}\n"
        )
    return "\n".join(parts)


def render_refusal_section(records: list[dict]) -> str:
    parts = []
    for i, r in enumerate(records, start=1):
        chunk_list = _format_chunk_list(r["retrieved_chunks"])
        parts.append(
            f"### Unsupported Question {i}\n\n"
            f"**Question:** {r['question']}\n\n"
            f"**Retrieved chunks:**\n\n"
            f"{chunk_list}\n\n"
            f"**Assistant response:**\n\n"
            f"> {r['answer']}\n\n"
            f"**Reason:** {r['reason']}\n"
        )
    return "\n".join(parts)


def render_bonus_section(bonus: dict) -> str:
    b = bonus["baseline"]
    s = bonus["structure_aware"]

    b_chunk = b["top_chunk"]
    s_chunk = s["top_chunk"]

    b_line = f"`{b_chunk['chunk_id']}` (score {b_chunk['score']})" if b_chunk else "none"
    s_line = f"`{s_chunk['chunk_id']}` (score {s_chunk['score']})" if s_chunk else "none"

    return (
        f"**Question:** {bonus['question']}\n\n"
        f"**Baseline top-1 chunk:** {b_line}\n\n"
        f"**Baseline answer:**\n\n> {b['answer']}\n\n"
        f"**Structure-aware top-1 chunk:** {s_line}\n\n"
        f"**Structure-aware answer:**\n\n> {s['answer']}\n\n"
        "**Analysis:** The structure-aware chunker retrieved the exact ERR-6030 row at rank 1 "
        "(higher precision), while baseline ranked the full error-code table third. "
        "If the full table chunk included surrounding procedural context that the single-row "
        "chunk omits, the baseline answer may be more complete despite weaker retrieval "
        "precision — a direct illustration of the precision/completeness tension.\n"
    )


def update_results_md(answerable_md: str, refusal_md: str, bonus_md: str) -> None:
    content = RESULTS_MD.read_text(encoding="utf-8")

    def replace_section(text: str, header: str, new_body: str) -> str:
        pattern = rf"(^## {re.escape(header)}\n)(.*?)(?=^## |\Z)"
        repl = f"## {header}\n\n{new_body.rstrip()}\n\n"
        return re.sub(pattern, repl, text, flags=re.DOTALL | re.MULTILINE)

    old_scope = (
        "Grounded generation and refusal handling (Phases 16-20 of the original plan,\n"
        "which require a local LLM via Ollama) were explicitly deferred for this pass.\n"
        "This report covers Phases 0-15: ingestion, metadata validation, both\n"
        "chunking strategies, embeddings, Hit-in-Top-5 retrieval evaluation, and\n"
        "metadata filtering."
    )
    new_scope = (
        "This report covers all phases: ingestion, metadata validation, both chunking "
        "strategies, embeddings, Hit-in-Top-5 retrieval evaluation, metadata filtering, "
        "grounded generation with citations, and refusal handling."
    )
    content = content.replace(old_scope, new_scope)

    content = replace_section(content, "9. Grounded Answers", answerable_md)
    content = replace_section(content, "10. Refusal Transcripts", refusal_md)
    content = replace_section(content, "13. Bonus — Precision vs Completeness", bonus_md)

    RESULTS_MD.write_text(content, encoding="utf-8")
    print(f"Updated {RESULTS_MD}")


def main() -> None:
    questions = _load_questions()

    print("\nRunning answerable questions...")
    answerable = run_answerable(questions)

    print("\nRunning refusal questions...")
    refusals = run_refusals()

    print("\nRunning bonus comparison...")
    bonus = run_bonus()

    output_path = EVALUATION_DIR / "generation_transcripts.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"answerable": answerable, "refusals": refusals, "bonus": bonus}, f, indent=2)
    print(f"\nWrote {output_path}")

    answerable_md = render_answerable_section(answerable)
    refusal_md = render_refusal_section(refusals)
    bonus_md = render_bonus_section(bonus)

    update_results_md(answerable_md, refusal_md, bonus_md)
    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except LLMRequestError as exc:
        print(f"\n[error] {exc}", file=sys.stderr)
        sys.exit(1)

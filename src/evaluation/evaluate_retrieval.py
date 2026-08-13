import json

from src.config import EVALUATION_DIR
from src.evaluation.hit_at_k import hit_at_5


def _load_json(filename: str):
    with open(EVALUATION_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


def evaluate() -> dict:
    questions = {q["id"]: q for q in _load_json("questions.json")}
    baseline_dump = {d["question_id"]: d for d in _load_json("baseline_search_dump.json")}
    structure_dump = {d["question_id"]: d for d in _load_json("structure_search_dump.json")}
    semantic_dump = {d["question_id"]: d for d in _load_json("semantic_search_dump.json")}

    per_question = []
    baseline_hits = 0
    structure_hits = 0
    semantic_hits = 0

    for question_id, question in questions.items():
        baseline_hit, baseline_rank = hit_at_5(
            question, baseline_dump[question_id]["results"]
        )
        structure_hit, structure_rank = hit_at_5(
            question, structure_dump[question_id]["results"]
        )
        semantic_hit, semantic_rank = hit_at_5(
            question, semantic_dump[question_id]["results"]
        )

        baseline_hits += int(baseline_hit)
        structure_hits += int(structure_hit)
        semantic_hits += int(semantic_hit)

        per_question.append(
            {
                "question_id": question_id,
                "question": question["question"],
                "table_dependent": question["table_dependent"],
                "baseline_rank": baseline_rank,
                "baseline_hit_at_5": baseline_hit,
                "structure_rank": structure_rank,
                "structure_hit_at_5": structure_hit,
                "semantic_rank": semantic_rank,
                "semantic_hit_at_5": semantic_hit,
            }
        )

    return {
        "per_question": per_question,
        "summary": {
            "baseline_hit_at_5": f"{baseline_hits}/{len(questions)}",
            "structure_aware_hit_at_5": f"{structure_hits}/{len(questions)}",
            "semantic_hit_at_5": f"{semantic_hits}/{len(questions)}",
        },
    }

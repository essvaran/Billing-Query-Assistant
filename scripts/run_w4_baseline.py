"""
Week 4 baseline evaluation: pure dense retrieval, hit-rate@3, p50 latency.

Run BEFORE making any retrieval change. The numbers produced here are the
'before' half of the before→after comparison.
"""

import json
import sys
import time
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import BASELINE_COLLECTION
from src.retrieval.search import search
from src.evaluation.hit_at_k import evidence_present

GOLDEN_SET = Path("evaluation/golden_set.jsonl")
OUTPUT = Path("evaluation/w4_baseline.json")
TOP_K = 3
REPEATS = 5  # per-query timing repeats for stable p50


def hit_at_3(question: dict, results: list[dict]) -> tuple[bool, int | None]:
    for r in results[:TOP_K]:
        if evidence_present(r["text"], question["required_evidence_terms"]):
            return True, r["rank"]
    return False, None


def main() -> None:
    questions = [json.loads(line) for line in GOLDEN_SET.read_text().splitlines()]

    all_latencies_ms: list[float] = []
    per_question: list[dict] = []

    for q in questions:
        # warm the embedding model before timing
        search(BASELINE_COLLECTION, q["question"], k=TOP_K)

        latencies: list[float] = []
        for _ in range(REPEATS):
            t0 = time.perf_counter()
            results = search(BASELINE_COLLECTION, q["question"], k=TOP_K)
            latencies.append((time.perf_counter() - t0) * 1000)

        hit, hit_rank = hit_at_3(q, results)
        med_ms = round(median(latencies), 1)
        all_latencies_ms.extend(latencies)

        top3 = [
            {"rank": r["rank"], "chunk_id": r["chunk_id"], "score": r["score"],
             "text_preview": r["text"][:200]}
            for r in results[:TOP_K]
        ]

        per_question.append(
            {
                "id": q["id"],
                "question": q["question"],
                "exact_token": q["exact_token"],
                "known_chunk_id": q["known_chunk_id"],
                "hit_at_3": hit,
                "hit_rank": hit_rank,
                "latency_p50_ms": med_ms,
                "top_3": top3,
            }
        )

        status = f"HIT  rank={hit_rank}" if hit else "MISS"
        print(f"  {q['id']}  {status:<14}  {med_ms:>6.1f}ms  {q['question']}")

    hits = sum(1 for r in per_question if r["hit_at_3"])
    overall_p50 = round(median(all_latencies_ms), 1)

    summary = {
        "retriever": "dense-only (baseline collection, cosine, k=3)",
        "hit_rate_at_3": f"{hits}/{len(questions)}",
        "p50_latency_ms": overall_p50,
        "per_question": per_question,
    }

    OUTPUT.write_text(json.dumps(summary, indent=2))
    print(f"\nBaseline hit-rate@3 : {hits}/{len(questions)}")
    print(f"Baseline p50 latency: {overall_p50} ms")
    print(f"Written -> {OUTPUT}")


if __name__ == "__main__":
    main()

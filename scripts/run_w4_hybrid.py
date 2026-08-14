"""
Week 4 hybrid evaluation: BM25 + RRF fusion, hit-rate@3, p50 latency.

Run AFTER run_w4_baseline.py. Compare numbers to see whether the single
retrieval change (BM25+RRF, k=60) improved hit-rate@3 and at what latency cost.
"""

import json
import sys
import time
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import BASELINE_COLLECTION
from src.retrieval.hybrid_search import hybrid_search
from src.retrieval.bm25_search import get_bm25_index
from src.evaluation.hit_at_k import evidence_present

GOLDEN_SET = Path("evaluation/golden_set.jsonl")
BASELINE_RESULTS = Path("evaluation/w4_baseline.json")
OUTPUT = Path("evaluation/w4_hybrid.json")
TOP_N = 3
REPEATS = 5


def hit_at_3(question: dict, results: list[dict]) -> tuple[bool, int | None]:
    for r in results[:TOP_N]:
        if evidence_present(r["text"], question["required_evidence_terms"]):
            return True, r["rank"]
    return False, None


def main() -> None:
    questions = [json.loads(line) for line in GOLDEN_SET.read_text().splitlines()]

    # pre-build BM25 index (one-time cost, not counted per query)
    print("Building BM25 index …")
    get_bm25_index(BASELINE_COLLECTION)

    # load baseline for comparison
    baseline = json.loads(BASELINE_RESULTS.read_text()) if BASELINE_RESULTS.exists() else {}
    baseline_map = {r["id"]: r for r in baseline.get("per_question", [])}

    all_latencies_ms: list[float] = []
    per_question: list[dict] = []

    for q in questions:
        # warm
        hybrid_search(BASELINE_COLLECTION, q["question"], top_n=TOP_N)

        latencies: list[float] = []
        for _ in range(REPEATS):
            t0 = time.perf_counter()
            results = hybrid_search(BASELINE_COLLECTION, q["question"], top_n=TOP_N)
            latencies.append((time.perf_counter() - t0) * 1000)

        hit, hit_rank = hit_at_3(q, results)
        med_ms = round(median(latencies), 1)
        all_latencies_ms.extend(latencies)

        top3 = [
            {"rank": r["rank"], "chunk_id": r["chunk_id"], "rrf_score": r["rrf_score"],
             "text_preview": r["text"][:200]}
            for r in results[:TOP_N]
        ]

        # determine per-question outcome relative to baseline
        b = baseline_map.get(q["id"], {})
        was_hit = b.get("hit_at_3", None)
        if was_hit is True and hit:
            outcome = "still-passing"
        elif was_hit is False and hit:
            outcome = "fixed"
        elif was_hit is False and not hit:
            outcome = "still-broken"
        else:
            outcome = "still-passing" if hit else "regressed"

        per_question.append(
            {
                "id": q["id"],
                "question": q["question"],
                "exact_token": q["exact_token"],
                "known_chunk_id": q["known_chunk_id"],
                "hit_at_3": hit,
                "hit_rank": hit_rank,
                "latency_p50_ms": med_ms,
                "outcome": outcome,
                "top_3": top3,
            }
        )

        print(f"  {q['id']}  {'HIT  rank='+str(hit_rank) if hit else 'MISS':<14}  "
              f"{med_ms:>6.1f}ms  [{outcome}]  {q['question']}")

    hits = sum(1 for r in per_question if r["hit_at_3"])
    overall_p50 = round(median(all_latencies_ms), 1)

    summary = {
        "retriever": "hybrid BM25+RRF (baseline collection, rrf_k=60, dense_k=25, bm25_k=25, top_n=3)",
        "hit_rate_at_3": f"{hits}/{len(questions)}",
        "p50_latency_ms": overall_p50,
        "per_question": per_question,
    }

    OUTPUT.write_text(json.dumps(summary, indent=2))
    print(f"\nHybrid  hit-rate@3 : {hits}/{len(questions)}")
    print(f"Hybrid  p50 latency: {overall_p50} ms")
    print(f"Written -> {OUTPUT}")


if __name__ == "__main__":
    main()

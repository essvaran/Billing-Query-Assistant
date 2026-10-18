"""Retrieval baseline on the synthetic tickets (Week 12, requirement 1).

Reports two numbers:
  hit@3            : gold article/policy slug appears in the top-3 hits
  wrong-policy rate: for refund tickets, share whose top-3 contains the OTHER
                     refund-policy version than the customer is entitled to,
                     with and without the policy_version filter.

Run:  python scripts/measure_retrieval.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import TIER1_COLLECTION, VARIANT_A_DIR
from src.retrieval.filters import policy_where
from src.retrieval.hybrid_search import hybrid_search

OUT = Path(__file__).resolve().parent.parent / "docs" / "archive" / "deliverables" / "week12" / "baseline" / "retrieval_baseline.json"


def main() -> None:
    tickets = [json.loads(l) for l in (VARIANT_A_DIR / "tickets_300.jsonl").read_text(encoding="utf-8").splitlines() if l]
    answerable = [t for t in tickets if t["gold_slug"] != "none"]

    hit = {"overall": [0, 0]}
    wrong = {"unfiltered": [0, 0], "filtered": [0, 0]}
    for t in answerable:
        entitled = t["expected_policy_version"]
        if t["kind"] == "refund":
            # unfiltered: what the pre-Week-12 retriever would do
            raw = hybrid_search(TIER1_COLLECTION, t["body"] + " refund window days policy", top_n=3)
            other = "refund-14d" if entitled == "refund-30d" else "refund-30d"
            wrong["unfiltered"][1] += 1
            wrong["unfiltered"][0] += any(h["policy_version"] == other for h in raw)
            fil = hybrid_search(TIER1_COLLECTION, t["body"] + " refund window days policy", top_n=3,
                                where=policy_where(entitled))
            wrong["filtered"][1] += 1
            wrong["filtered"][0] += any(h["policy_version"] == other for h in fil)
            hits = fil
        else:
            hits = hybrid_search(TIER1_COLLECTION, t["body"], top_n=3)
        key = t["kind"]
        hit.setdefault(key, [0, 0])
        ok = any(h["slug"] == t["gold_slug"] for h in hits)
        for k in ("overall", key):
            hit[k][0] += ok
            hit[k][1] += 1

    def rate(p):
        return round(p[0] / p[1], 3) if p[1] else None

    result = {
        "corpus": "synthetic variant A (see data/variant_a/synthetic/SYNTHETIC.txt)",
        "hit_at_3": {k: {"hits": v[0], "n": v[1], "rate": rate(v)} for k, v in hit.items()},
        "wrong_policy_in_top3": {k: {"count": v[0], "n": v[1], "rate": rate(v)} for k, v in wrong.items()},
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

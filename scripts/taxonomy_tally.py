"""Count the failure modes of an eval run, with frequency and one trace id each.

    python scripts/taxonomy_tally.py after fix1

Counting is mechanical; NAMING and SEVERITY are the result of reading traces (see docs/archive/deliverables/week12/taxonomy.md).
Some modes cannot be seen by an assertion at all (invisible characters, a model burning tokens searching, a judge-only
finding), so they are detected here from the stored results.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "docs" / "archive" / "deliverables" / "week12" / "eval"
INVISIBLE = {"​": "zero-width space", "‑": "non-breaking hyphen", " ": "narrow no-break space", "⁠": "word joiner"}


def load(tag: str):
    rows = [json.loads(l) for l in (EVAL / f"results_{tag}.jsonl").read_text(encoding="utf-8").splitlines() if l]
    cases = {json.loads(l)["case_id"]: json.loads(l) for l in
             (ROOT / "evaluation" / "integrated" / "cases.jsonl").read_text(encoding="utf-8").splitlines() if l}
    return rows, cases


def family(slug: str) -> str:
    return slug.rsplit("-", 1)[0]


def modes(rows, cases):
    out: dict[str, list[dict]] = {k: [] for k in (
        "wrong_source_sibling_article", "wrong_source_internal_macro", "wrong_source_other_document",
        "over_escalation", "token_blowup_while_searching", "judge_flagged_unsupported_detail",
        "invisible_characters_in_reply", "wrong_policy_version", "unsafe_when_must_escalate")}
    for r in rows:
        case = cases[r["case_id"]]
        failed = {c["name"] for c in r["failed_checks"]}
        if "cites_gold_source" in failed and r["decision"] == "ANSWER":
            gold = case["gold_slug"]
            cited = [c.split("[")[1].split(" @")[0].rstrip("]") for c in r["citations"]]
            if any(c.startswith("macro-") for c in cited):
                out["wrong_source_internal_macro"].append(r)
            elif any(family(c) == family(gold) for c in cited):
                out["wrong_source_sibling_article"].append(r)
            else:
                out["wrong_source_other_document"].append(r)
        if "decision_matches" in failed and case["expected_decision"] == "ANSWER":
            out["over_escalation"].append(r)
        if "decision_matches" in failed and case["expected_decision"] == "ESCALATE":
            out["unsafe_when_must_escalate"].append(r)
        if failed & {"no_superseded_citation", "names_policy_version", "states_correct_window"}:
            out["wrong_policy_version"].append(r)
        if r["tools_called"].count("search_help_centre") > 2 or r["total_tokens"] > 9000:
            out["token_blowup_while_searching"].append(r)
        if r["judge"] and r["judge"]["verdict"] == "NOT_GOOD":
            out["judge_flagged_unsupported_detail"].append(r)
        if any(ch in (r["reply"] or "") for ch in INVISIBLE):
            out["invisible_characters_in_reply"].append(r)
    return out


def main(tags: list[str]) -> None:
    for tag in tags:
        rows, cases = load(tag)
        answerable = sum(1 for c in cases.values() if c["expected_decision"] == "ANSWER" and any(r["case_id"] == c["case_id"] for r in rows))
        print(f"\n### {tag}: n = {len(rows)} cases, {answerable} expected to be answered\n")
        print("| Mode | Count | of n | Cases | Example trace |\n|---|---|---|---|---|")
        for name, hits in modes(rows, cases).items():
            if hits:
                print(f"| {name} | {len(hits)} | {100 * len(hits) / len(rows):.0f}% | {', '.join(h['case_id'] for h in hits)} | `{hits[0]['trace_id']}` |")


if __name__ == "__main__":
    main(sys.argv[1:] or ["after"])

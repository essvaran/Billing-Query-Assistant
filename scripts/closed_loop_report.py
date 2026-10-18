"""Write the closed failure-to-test loop report.

    python scripts/closed_loop_report.py holdout_20b_base holdout_20b_fixed

Evidence used, all read from stored results:
  * the failure, from the full-system run `after` (production model, 39 cases)
  * an A/B of the two fixes on HELD-OUT tickets (not used to find or tune anything), run on a second model
    because the production model's daily token cap was already spent (see seams.md 44 and 46)
"""
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "docs" / "archive" / "deliverables" / "week12" / "eval"
OUT = ROOT / "docs" / "archive" / "deliverables" / "week12" / "closed_loop.md"


def load(tag: str):
    rows = {json.loads(l)["case_id"]: json.loads(l) for l in (EVAL / f"results_{tag}.jsonl").read_text(encoding="utf-8").splitlines() if l}
    summary = json.loads((EVAL / f"summary_{tag}.json").read_text(encoding="utf-8"))
    return rows, summary


def macro_cited(row) -> bool:
    return any("macro-" in c for c in row["citations"])


def metrics(rows):
    gold = [r for r in rows.values() if "cites_gold_source" in r["checks"]]
    answered = [r for r in rows.values() if r["decision"] == "ANSWER"]
    model_rows = [r for r in rows.values() if r["total_tokens"] > 0]
    return {
        "n": len(rows),
        "passed": sum(r["passed"] for r in rows.values()),
        "gold": f"{sum(r['checks']['cites_gold_source'] for r in gold)} of {len(gold)}",
        "macro": sum(macro_cited(r) for r in rows.values()),
        "answered": len(answered),
        "escalated": len(rows) - len(answered),
        "rate_limited": sum(1 for r in rows.values() if r["reason"] == "rate_limited"),
        "tokens": round(statistics.mean(r["total_tokens"] for r in model_rows)) if model_rows else 0,
    }


def main(base: str, fixed: str) -> int:
    a_rows, a_sum = load(base)
    b_rows, b_sum = load(fixed)
    full, full_sum = load("after")
    a, b = metrics(a_rows), metrics(b_rows)
    gold_full = [r for r in full.values() if "cites_gold_source" in r["checks"]]
    wrong = [r for r in gold_full if not r["checks"]["cites_gold_source"]]

    changed = [c for c in a_rows if a_rows[c]["passed"] != b_rows[c]["passed"]]
    up = sum(1 for c in changed if b_rows[c]["passed"])
    down = len(changed) - up
    if not changed:
        verdict = "no case changed."
    elif up and down and b["n"] < 30:
        verdict = (f"INCONCLUSIVE. {up} cases improved and {down} got worse (net {up - down:+d} of {b['n']}). With one run per arm and "
                   "n this small, a swing in both directions is what run-to-run variation looks like. "
                   + ("No reply cited an internal macro in either arm, so the macro fix had nothing to fix on this draw. " if not a["macro"] and not b["macro"] else ""))
    elif up > down:
        verdict = f"the fixes helped on {up - down} net cases of {b['n']}, in the expected direction."
    else:
        verdict = f"the fixes did not help ({up} improved, {down} worse)."

    def why(row):
        return "; ".join(f"{c['name']}" for c in row["failed_checks"]) or "all assertions pass"

    # the production-model re-run of the whole suite, when it exists (needed the token cut and --resume to fit the cap)
    prod: list[str] = []
    if (EVAL / "results_fix1.jsonl").exists():
        fx, fx_sum = load("fix1")
        gold_fx = [r for r in fx.values() if "cites_gold_source" in r["checks"]]
        wrong_fx = [r for r in gold_fx if not r["checks"]["cites_gold_source"]]
        rows = [f"| {r['case_id']} | {why(r)} | {why(fx[r['case_id']]) if r['case_id'] in fx else 'not run'} |" for r in wrong]
        prod = [
            "## 5. The same 39 cases on the production model, after the fixes", "",
            "Once the token cut (prefetch, `seams.md` 54) and resumable runs fitted a full run inside the daily cap, the whole suite ran again "
            "on `gpt-oss-120b` with both source fixes and prefetch on (tag `fix1`). This is the red-to-green check on the production system.", "",
            "| Measure (n = 39, production model) | Before (`after`) | After (`fix1`) |", "|---|---|---|",
            f"| Cases passing every assertion | {full_sum['passed']} of {full_sum['n']} | {fx_sum['passed']} of {fx_sum['n']} |",
            f"| Answerable cases citing the wrong source | {len(wrong)} of {len(gold_full)} | {len(wrong_fx)} of {len(gold_fx)} |",
            f"| Mean tokens per model ticket | {full_sum['cost_latency']['mean_tokens_per_llm_ticket']} | {fx_sum['cost_latency']['mean_tokens_per_llm_ticket']} |",
            f"| Cost per deflected ticket | ${full_sum['cost_latency']['cost_per_deflected_usd']} | ${fx_sum['cost_latency']['cost_per_deflected_usd']} |", "",
            "The cases that were red, before and after:", "",
            "| Case | Before | After |", "|---|---|---|", *rows, "",
            "**Read this with its limits.** These are the SAME cases the failure was found in and the fixes were derived from, so the "
            "improvement is optimistic; the held-out A/B above, which avoids that, was inconclusive. Three things changed at once "
            "(macro exclusion, error code in the query, prefetch), so the run cannot say which one moved which case. One run, no "
            f"variance measured. What it does show: on the production model, {sum(1 for r in wrong if fx.get(r['case_id'], {}).get('passed'))} "
            f"of the {len(wrong)} red cases now pass; a case that still fails may have moved from a wrong answer to an escalation, "
            "which is safer but still a missed deflection (read the table). The cases stay in the suite to guard the result.", ""]

    L = [
        "# Closed failure-to-test loop", "",
        "Generated by `scripts/closed_loop_report.py`. All data is synthetic.", "",
        "## 1. The failure, found in traces", "",
        f"In the full-system run (production model, 39 cases) **{len(wrong)} of {len(gold_full)} answerable cases cited the wrong source** "
        f"({', '.join(r['case_id'] for r in wrong)}): three cited a near-identical sibling article, one cited an internal Zendesk macro to a "
        "customer and invented steps that were in no source (RAN14), one cited the shipping matrix instead of the delivery article. One status "
        "ticket escalated after about 11,500 tokens of searching (RAN10). Traces: `taxonomy.md` modes 1 to 3.", "",
        "## 2. The failure is already a test", "",
        "Each of those is a case in `evaluation/integrated/cases.jsonl` with the assertion `cites_gold_source`, so the suite was red on them. "
        "A failure an agent reports from the UI becomes a permanent case the same way: Report wrong answer, then Review inbox, then "
        "Create evaluation case (`tier1/eval_cases.py`; checked in a browser, and by `tests/test_tier1_api.py`).", "",
        "## 3. Two fixes, each with a reason", "",
        "- **Internal macros are excluded from customer-facing search.** They are agent templates, not documents a customer should be pointed at, "
        "and stale text hides in them: an old macro quoting the retired 14-day window is how the original refund escalation happened.",
        "- **The prompt tells the model to put the ticket's error code in its search query**, because an error code identifies the one article that explains it.", "",
        "## 4. Measured on tickets the fixes were not derived from", "",
        f"{b['n']} held-out tickets (FAQ, order status, delivery time), a different random draw from the main suite, none of them seen while finding the problem. "
        "Same cases, same model, same code; the only difference is the two fixes switched off or on (`TIER1_ABLATE=macro_filter,error_code_prompt`). "
        "**The model here is `openai/gpt-oss-20b`, not the production `gpt-oss-120b`**, because the production model's 200,000-token daily cap was spent by "
        "the time this was run (`seams.md` 44). So this shows whether the fixes help, not what the production system scores.", "",
        "| Measure (held-out, n = " + str(b["n"]) + ") | Without the fixes | With the fixes |", "|---|---|---|",
        f"| Cases passing every assertion | {a['passed']} of {a['n']} | {b['passed']} of {b['n']} |",
        f"| Cited the expected source | {a['gold']} | {b['gold']} |",
        f"| Replies citing an internal macro | {a['macro']} | {b['macro']} |",
        f"| Answered / escalated | {a['answered']} / {a['escalated']} | {b['answered']} / {b['escalated']} |",
        f"| Stopped by the provider's rate limit | {a['rate_limited']} | {b['rate_limited']} |",
        f"| Mean tokens per ticket | {a['tokens']} | {b['tokens']} |", "",
        "Cases whose result changed: " + (", ".join(f"{c} ({'now passes' if b_rows[c]['passed'] else 'now fails: ' + why(b_rows[c])})" for c in changed) or "none"), "",
        f"**Verdict: {verdict}**", "",
        *prod,
        f"## {6 if prod else 5}. How far to trust this", "",
        "- **n = 15 and one run each.** A difference of one or two cases is inside what run-to-run variation could produce; variance is not measured "
        "(a rerun with `LLM_CACHE=off` twice would measure it).",
        "- **Weaker model.** If `gpt-oss-20b` fails mostly for reasons unrelated to source choice (for example citation format), the comparison has little room to move: "
        "read the failure reasons in the two reports before reading the totals.",
        ("- The first full re-run on the production model (2026-10-16) did not complete (6 of 39 cases before the daily cap) and was discarded; "
         "the `fix1` run in section 5 is a later, complete run." if prod else
         "- **A full re-run of the fixed system on the production model did not complete** (6 of 39 cases ran before the daily token cap); that partial run was discarded, not reported."),
        "- The judges are not used here (assertions only), and neither has been validated against a human yet.",
        "- The corpus is synthetic and templated; real near-duplicate articles may behave differently."]
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[18:40]))
    return 0


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:3] or ["holdout_20b_base", "holdout_20b_fixed"])))

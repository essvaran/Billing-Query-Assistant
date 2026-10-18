"""One command: run the integrated eval suite against the real entry point.

    python -m tier1 eval                 # full suite, judge on, tag "after"
    python -m tier1 eval --tag before --ablate version_filter,policy_guard
    python -m tier1 eval --only both_versions --no-judge

Every case goes through tier1.service.handle_ticket, the same function the CLI and API call.
Order of evaluation, on purpose:  assertions first (exact, free), judge second (only on answers).

Cases, runs, per-case results and human labels live in the catalog database (src/catalog/eval_store.py); edit cases
in the app (Admin, Eval cases). For people to read, each run also writes, under docs/archive/deliverables/week12/eval/:
    results_<tag>.jsonl   one row per case with checks, trace id, cost, latency, judge verdict
    summary_<tag>.json    every number in the report
    report_<tag>.md       the eval report, including what the suite does NOT cover (catalog list eval_not_covered)
    label_sheet.md        the replies for a HUMAN to label (judge verdicts and assertion results hidden)
Labels are given on the admin page /label. Failure-mode names and severities are the catalog list
integrated_failure_mode; which failed check maps to which mode is fixed in MODE_RULES below.

Long runs and the free tier's daily token cap:
    python -m tier1 eval --tag fix1 --resume     continue a run the cap stopped (finished cases are kept)
    python -m tier1 eval --rescore fix1          recompute summary, judge agreement and report, no model calls
    python -m tier1 eval --cases regression      only the cases created from reported failures (REG..)
"""
import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "docs" / "archive" / "deliverables" / "week12" / "eval"

from evaluation.integrated import labels as human_labels  # noqa: E402
from src.catalog import eval_store, ref, settings  # noqa: E402

# failed checks -> failure mode code. The order, label and severity of each mode come from the catalog list
# 'integrated_failure_mode'; a mode with no rule here never matches (it can still be relabelled).
MODE_RULES = {
    "unsafe_answer_when_must_escalate": lambda c, f: c["expected_decision"] == "ESCALATE" and f.get("decision_matches"),
    "wrong_policy_version": lambda c, f: bool({"no_superseded_citation", "names_policy_version", "states_correct_window"} & f.keys()),
    "money_claim": lambda c, f: "no_money_claim" in f,
    "pii_in_reply": lambda c, f: "no_pii_in_reply" in f,
    "wrong_eligibility": lambda c, f: "eligibility_consistent" in f,
    "entitlement_not_checked": lambda c, f: "expected_tools_called" in f and c["expected_decision"] == "ANSWER" and "check_entitlement" in c["expected_tools"],
    "over_escalation": lambda c, f: c["expected_decision"] == "ANSWER" and f.get("decision_matches"),
    "wrong_source_cited": lambda c, f: "cites_gold_source" in f,
    "wrong_shipping_days": lambda c, f: "shipping_days_correct" in f,
    "bad_escalation_handling": lambda c, f: bool({"escalation_reason_ok", "handoff_created", "nothing_customer_facing"} & f.keys()),
    "missing_expected_tool": lambda c, f: "expected_tools_called" in f,
    "other": lambda c, f: True,
}
TOOL_CHECKS = {"expected_tools_called", "no_forbidden_tools"}


def not_covered() -> list[str]:
    return [v["label"] for v in ref.values("eval_not_covered")]


def load_cases(only: str | None, limit: int | None, source: str = "main", case_ids: list[str] | None = None) -> list[dict]:
    if source == "regression":
        cases = eval_store.cases("regression")
        if case_ids:
            cases = [c for c in cases if c["case_id"] in case_ids]
        return cases[:limit] if limit else cases
    if case_ids:
        every = eval_store.cases("main") + eval_store.cases("holdout") + eval_store.cases("regression")
        return [c for c in every if c["case_id"] in case_ids]
    if source == "holdout":      # tickets the failure analysis never saw; no regression cases mixed in
        return eval_store.cases("holdout")[:limit] if limit else eval_store.cases("holdout")
    cases = eval_store.cases("main") + eval_store.cases("regression")   # permanent guards added from real failures
    if only:
        cases = [c for c in cases if c["slice"] == only]
    return cases[:limit] if limit else cases


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}%" if d else "n/a"


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(p * (len(ordered) - 1))))]


class RateLimitAbort(Exception):
    """The provider's cap was reached mid-run. Results after this point would measure the cap, not the system."""

    def __init__(self, done: list[dict], at_case: str, detail: str):
        super().__init__(f"rate limited at {at_case}: {detail}")
        self.done, self.at_case, self.detail = done, at_case, detail


# --- running ------------------------------------------------------------------------------------

def run_cases(cases: list[dict], judge: bool, done: list[dict] | None = None) -> list[dict]:
    """done: rows already finished by an earlier, interrupted run (--resume); their cases are not run again."""
    from evaluation.integrated.assertions import failed, run_assertions
    from tier1 import db
    from tier1.models import TicketRequest
    from tier1.service import handle_ticket

    db.seed_from_synthetic()
    with db.get_conn() as conn:
        known = [v for r in conn.execute("SELECT name, email, address FROM customers") for v in (r[0], r[1], r[2]) if v]

    rows = list(done or [])
    finished = {r["case_id"] for r in rows}
    order = {c["case_id"]: n for n, c in enumerate(cases)}
    for i, case in enumerate(cases, 1):
        if case["case_id"] in finished:
            continue
        resp = handle_ticket(TicketRequest(
            body=case["body"], subject=case["subject"], customer_id=case["customer_id"],
            order_id=case["order_id"], ticket_id=case["ticket_id"] or case["case_id"])).to_dict()
        if resp["reason"] == "rate_limited":
            raise RateLimitAbort(sorted(rows, key=lambda r: order.get(r["case_id"], 0)), case["case_id"], resp.get("error") or "")
        checks = run_assertions(case, resp, known)
        bad = failed(checks)
        row = {
            "case_id": case["case_id"], "slice": case["slice"], "pair_id": case["pair_id"],
            "expected_decision": case["expected_decision"], "expected_policy_version": case["expected_policy_version"],
            "decision": resp["decision"], "reason": resp["reason"], "passed": not bad,
            "checks": {c.name: c.passed for c in checks},
            "failed_checks": [{"name": c.name, "detail": c.detail} for c in bad],
            "tools_called": resp["tools_called"], "model_tools_called": resp.get("model_tools_called", resp["tools_called"]),
            "citations": [c["display"] for c in resp["citations"]],
            "violations": [v["code"] for v in resp["violations"]],
            "trace_id": resp["trace_id"], "latency_ms": resp["latency_ms"], "total_tokens": resp["total_tokens"],
            "cost_usd": resp["cost_usd"], "laps": resp["laps"],
            "error": (resp.get("error") or "")[:200], "budget_hit": (resp.get("budget_hit") or "")[:120],
            "reply": resp["reply"], "customer_reply": resp.get("customer_reply", ""), "draft": resp["draft"],
            "entitlement": resp["entitlement"], "order_facts": resp.get("order_facts"),
            "subject": case["subject"], "body": case["body"],
            "sources": [{**s, "text": (s.get("text") or "")[:400]} for s in resp["sources"]],
            "judge": None, "judge_alt": None,
        }
        if judge and resp["decision"] == "ANSWER" and resp["reply"]:
            from evaluation.integrated.judge import judge_reply, judge_reply_week6
            row["judge"] = judge_reply_week6(case, resp)     # primary: the Week 6 validated rubric
            row["judge_alt"] = judge_reply(case, resp)       # second opinion: the integrated rubric
        status = "PASS" if row["passed"] else "FAIL"
        print(f"[{i:2}/{len(cases)}] {status} {case['case_id']:<6} {case['slice']:<14} {resp['decision']:<8} "
              f"{(resp['reason'] or '-'):<22} tok={resp['total_tokens']:<6} {resp['latency_ms'] / 1000:5.1f}s"
              + (f"  judge={row['judge']['verdict']}" if row["judge"] else "")
              + ("" if row["passed"] else "  <- " + ", ".join(c.name for c in bad)), flush=True)
        rows.append(row)
    return sorted(rows, key=lambda r: order.get(r["case_id"], 0))


# --- metrics ------------------------------------------------------------------------------------

def model_choice(rows: list[dict], by_id: dict) -> dict:
    """Tool choices the MODEL made, separate from calls code made for it (prefetch).

    With prefetch on, check_entitlement and the first search are made by code, so the combined path is right by
    construction and says nothing about the model. What is left to the model: whether to escalate (the escalate tool),
    whether to search again or look up the order, and (with prefetch off) whether it made the required calls itself.
    A case counts only if it reached the model. Escalation by a guard after the model answered counts as the model
    choosing wrong, because the model did not escalate.
    """
    reached = [r for r in rows if r["total_tokens"] > 0]
    quad, n_prefetched = Counter(), 0
    for r in reached:
        case = by_id[r["case_id"]]
        model = r.get("model_tools_called", r["tools_called"])
        prefetched = len(r["tools_called"]) - len(model)
        n_prefetched += prefetched > 0
        escalate_ok = ("escalate" in model) == (case["expected_decision"] == "ESCALATE")
        required_ok = prefetched > 0 or all(t in model for t in case["expected_tools"])
        forbidden_ok = not any(t in model for t in case.get("forbidden_tools") or [])
        outcome_ok = all(ok for name, ok in r["checks"].items() if name not in TOOL_CHECKS)
        quad[(outcome_ok, escalate_ok and required_ok and forbidden_ok)] += 1
    n = len(reached)
    path = (quad[(True, True)] + quad[(False, True)]) / n if n else 0
    outcome = (quad[(True, True)] + quad[(True, False)]) / n if n else 0
    return {
        "n": n, "prefetched_cases": n_prefetched, "accuracy": round(path, 3), "outcome_accuracy": round(outcome, 3),
        "gap_points": round((outcome - path) * 100, 1),
        "right_answer_wrong_path": quad[(True, False)], "right_path_wrong_answer": quad[(False, True)],
        "mean_model_calls": round(statistics.mean(len(r.get("model_tools_called", r["tools_called"])) for r in reached), 2) if n else 0,
    }


def mode_of(case: dict, row: dict) -> tuple[str, str]:
    failed = {c["name"]: True for c in row["failed_checks"]}
    for mode in ref.values("integrated_failure_mode", include_inactive=True):
        test = MODE_RULES.get(mode["code"])
        if test and test(case, failed):
            return mode["code"], mode["meta"].get("severity", "low")
    return "other", ref.meta("integrated_failure_mode", "other", "severity", "low")


def agreement(rows: list[dict], judge_key: str = "judge") -> dict:
    return human_labels.agreement(rows, judge_key)


def summarise(cases: list[dict], rows: list[dict], tag: str, ablate: str) -> dict:
    by_id = {c["case_id"]: c for c in cases}
    n = len(rows)
    s: dict = {"tag": tag, "ablate": ablate or None, "n": n, "passed": sum(r["passed"] for r in rows)}
    s["pass_rate"] = round(s["passed"] / n, 3) if n else 0

    slices = defaultdict(lambda: [0, 0])
    for r in rows:
        slices[r["slice"]][1] += 1
        slices[r["slice"]][0] += r["passed"]
    s["by_slice"] = {k: {"passed": v[0], "n": v[1], "rate": round(v[0] / v[1], 3)} for k, v in slices.items()}

    per_check = defaultdict(lambda: [0, 0])
    for r in rows:
        for name, ok in r["checks"].items():
            per_check[name][1] += 1
            per_check[name][0] += ok
    s["by_check"] = {k: {"passed": v[0], "n": v[1]} for k, v in sorted(per_check.items())}

    # both policy versions live: the slice the brief asks about, by customer version and by pair
    both = [r for r in rows if r["slice"] == "both_versions"]
    pairs = defaultdict(list)
    for r in both:
        pairs[r["pair_id"]].append(r["passed"])
    s["both_versions"] = {
        "n": len(both), "passed": sum(r["passed"] for r in both),
        "legacy_14d": {"n": sum(r["expected_policy_version"] == "refund-14d" for r in both),
                       "passed": sum(r["passed"] for r in both if r["expected_policy_version"] == "refund-14d")},
        "current_30d": {"n": sum(r["expected_policy_version"] == "refund-30d" for r in both),
                        "passed": sum(r["passed"] for r in both if r["expected_policy_version"] == "refund-30d")},
        "pairs_both_correct": sum(1 for v in pairs.values() if all(v) and len(v) == 2), "pairs": len(pairs),
    }

    # superseded-policy citation: the named metric for the demo
    refund_related = [r for r in rows if r["expected_policy_version"] != "none" and r["expected_decision"] == "ANSWER"]
    answered = [r for r in refund_related if r["decision"] == "ANSWER"]
    shown_wrong = [r for r in answered if r["checks"].get("no_superseded_citation") is False]
    drafted_wrong = [r for r in refund_related if "superseded_policy" in r["violations"] or "wrong_window" in r["violations"]]
    s["superseded_policy"] = {
        "refund_cases": len(refund_related), "answered": len(answered),
        "final_answers_citing_wrong_version": len(shown_wrong),
        "final_rate": round(len(shown_wrong) / len(answered), 3) if answered else None,
        "drafts_blocked_by_guard": len(drafted_wrong),
        "attempted_rate": round((len(shown_wrong) + len(drafted_wrong)) / len(refund_related), 3) if refund_related else None,
    }

    # failure modes
    modes: dict[str, dict] = {}
    for r in rows:
        if r["passed"]:
            continue
        name, severity = mode_of(by_id[r["case_id"]], r)
        m = modes.setdefault(name, {"count": 0, "severity": severity, "cases": [], "trace_ids": []})
        m["count"] += 1
        m["cases"].append(r["case_id"])
        m["trace_ids"].append(r["trace_id"])
    s["failure_modes"] = dict(sorted(modes.items(), key=lambda kv: -kv[1]["count"]))

    # trajectory: did it take the right path, separate from whether the answer was right
    traj = [r for r in rows if by_id[r["case_id"]]["expected_tools"]]
    quad = Counter()
    for r in traj:
        outcome_ok = all(ok for name, ok in r["checks"].items() if name not in TOOL_CHECKS)
        path_ok = all(r["checks"].get(name, True) for name in TOOL_CHECKS)
        quad[(outcome_ok, path_ok)] += 1
    t_n = len(traj)
    outcome_rate = (quad[(True, True)] + quad[(True, False)]) / t_n if t_n else 0
    path_rate = (quad[(True, True)] + quad[(False, True)]) / t_n if t_n else 0
    s["trajectory"] = {
        "n": t_n, "tool_choice_accuracy": round(path_rate, 3), "outcome_accuracy": round(outcome_rate, 3),
        "gap_points": round((outcome_rate - path_rate) * 100, 1),
        "right_answer_wrong_path": quad[(True, False)], "right_path_wrong_answer": quad[(False, True)],
        "both_right": quad[(True, True)], "both_wrong": quad[(False, False)],
        "wasted_search_calls": sum(max(0, r["tools_called"].count("search_help_centre") - settings.get("tier1.max_searches")) for r in rows),
    }
    s["trajectory"]["model_choice"] = model_choice(rows, by_id)

    # cost, latency, throughput
    llm_rows = [r for r in rows if r["total_tokens"] > 0]
    deflected = [r for r in rows if r["decision"] == "ANSWER" and r["passed"]]
    judged_good = [r for r in deflected if r["judge"] and r["judge"]["verdict"] == "GOOD"]
    total_cost = sum(r["cost_usd"] for r in rows)
    lat = [r["latency_ms"] / 1000 for r in llm_rows[1:]]          # drop the first: it pays the cold start
    mean_tok = statistics.mean(r["total_tokens"] for r in llm_rows) if llm_rows else 0
    s["cost_latency"] = {
        "total_cost_usd": round(total_cost, 6),
        "mean_cost_per_ticket_usd": round(total_cost / n, 6) if n else 0,
        "deflected_assertions_only": len(deflected),
        "cost_per_deflected_usd": round(total_cost / len(deflected), 6) if deflected else None,
        "deflected_assertions_and_judge": len(judged_good),
        "cost_per_deflected_judge_usd": round(total_cost / len(judged_good), 6) if judged_good else None,
        "llm_tickets": len(llm_rows), "tickets_with_no_model_call": n - len(llm_rows),
        "mean_tokens_per_llm_ticket": round(mean_tok), "p50_latency_s": round(percentile(lat, 0.5), 1),
        "p95_latency_s": round(percentile(lat, 0.95), 1), "first_ticket_latency_s": round(llm_rows[0]["latency_ms"] / 1000, 1) if llm_rows else None,
        "tpm_ceiling_tickets_per_min": round(settings.get("provider.tpm") / mean_tok, 2) if mean_tok else None,
    }

    s["judge"] = judge_summary(rows, "judge")
    if any(r.get("judge_alt") for r in rows):
        s["judge_alt"] = judge_summary(rows, "judge_alt")
    return s


def judge_summary(rows: list[dict], key: str) -> dict:
    judged = [r for r in rows if r.get(key)]
    first = judged[0][key] if judged else {}
    return {"model": first.get("model"), "version": first.get("version", "v3b-integrated"), "n": len(judged),
            "good": sum(r[key]["verdict"] == "GOOD" for r in judged),
            "not_good": sum(r[key]["verdict"] == "NOT_GOOD" for r in judged),
            "error": sum(r[key]["verdict"] == "ERROR" for r in judged),
            "agreement": agreement(rows, key)}


# --- outputs ------------------------------------------------------------------------------------

def render_report(s: dict, rows: list[dict]) -> str:
    L: list[str] = []
    cl, tj, sp, bv, jg = s["cost_latency"], s["trajectory"], s["superseded_policy"], s["both_versions"], s["judge"]
    L += [f"# Integrated eval report ({s['tag']})", "",
          f"- Cases: **n = {s['n']}**  |  passed all assertions: **{s['passed']} ({pct(s['passed'], s['n'])})**",
          f"- Configuration: {'ABLATED: ' + s['ablate'] if s['ablate'] else 'full system (version filter and policy guard on)'}",
          "- Corpus and tickets are SYNTHETIC (see data/variant_a/synthetic/SYNTHETIC.txt).", "",
          "## Pass rate by slice", "", "| Slice | Passed | n | Rate |", "|---|---|---|---|"]
    for name, v in s["by_slice"].items():
        L.append(f"| {name} | {v['passed']} | {v['n']} | {pct(v['passed'], v['n'])} |")

    L += ["", "## Both refund-policy versions live (the slice the brief asks about, not the average)", "",
          f"- Cases: {bv['passed']}/{bv['n']} pass ({pct(bv['passed'], bv['n'])})",
          f"- Legacy 14-day customers: {bv['legacy_14d']['passed']}/{bv['legacy_14d']['n']}",
          f"- Current 30-day customers: {bv['current_30d']['passed']}/{bv['current_30d']['n']}",
          f"- Question pairs where BOTH customers got the right answer: {bv['pairs_both_correct']}/{bv['pairs']}", "",
          "## Superseded-policy citation (the named metric)", "",
          f"- Refund cases expected to be answered: {sp['refund_cases']}; answered: {sp['answered']}",
          f"- Final answers citing the wrong policy version: **{sp['final_answers_citing_wrong_version']}/{sp['answered']}**"
          f" (rate {sp['final_rate'] if sp['final_rate'] is not None else 'n/a'})",
          f"- Drafts the guard blocked for the wrong version or window: {sp['drafts_blocked_by_guard']}",
          f"- Attempted rate (shown + blocked) over refund cases: {sp['attempted_rate']}", "",
          "## Failure modes (computed from assertions; trace ids are for reading)", "",
          "| Mode | Count | % of n | Severity | Cases | Example trace |", "|---|---|---|---|---|---|"]
    for name, m in s["failure_modes"].items():
        L.append(f"| {name} | {m['count']} | {pct(m['count'], s['n'])} | {m['severity']} | {', '.join(m['cases'])} | {m['trace_ids'][0]} |")
    if not s["failure_modes"]:
        L.append("| (none) | 0 | 0% | | | |")

    L += ["", "## Trajectory (tool choice) and the outcome-vs-trajectory gap", "",
          f"- Cases with an expected tool path: n = {tj['n']}",
          f"- Tool-choice accuracy: **{pct(round(tj['tool_choice_accuracy'] * tj['n']), tj['n'])}**; outcome accuracy: **{pct(round(tj['outcome_accuracy'] * tj['n']), tj['n'])}**",
          f"- Gap (outcome minus trajectory): **{tj['gap_points']} points**",
          f"- Right answer by the wrong path (lucky): {tj['right_answer_wrong_path']}; right path, wrong answer: {tj['right_path_wrong_answer']};"
          f" both right: {tj['both_right']}; both wrong: {tj['both_wrong']}",
          f"- Search calls beyond the cap of 2 that the agent tried anyway: {tj['wasted_search_calls']}"]
    mc = tj.get("model_choice")
    if mc:
        L += ["", "### Choices the model made itself (prefetched calls excluded)", "",
              f"- Cases that reached the model: n = {mc['n']}; of them, prefetched by code: {mc['prefetched_cases']}",
              f"- Model tool-choice accuracy: **{pct(round(mc['accuracy'] * mc['n']), mc['n'])}**; outcome accuracy on the same cases: "
              f"**{pct(round(mc['outcome_accuracy'] * mc['n']), mc['n'])}**; gap **{mc['gap_points']} points**",
              f"- Right answer by the wrong path: {mc['right_answer_wrong_path']}; right path, wrong answer: {mc['right_path_wrong_answer']};"
              f" mean tool calls the model made: {mc['mean_model_calls']}",
              "- When code prefetches the entitlement check and first search, the combined tool-choice figure above is right by"
              " construction; this one is the honest measure of the model."]
    L += ["",
          "## Cost and latency", "",
          f"- Total cost for the run: ${cl['total_cost_usd']}  |  mean per ticket: ${cl['mean_cost_per_ticket_usd']}",
          f"- Tickets that used no model call (pre-guard escalations): {cl['tickets_with_no_model_call']} of {s['n']}",
          f"- Deflected tickets (answered and all assertions pass): {cl['deflected_assertions_only']}"
          f"; cost per deflected ticket: **${cl['cost_per_deflected_usd']}** (all spend divided by deflected, escalations included)",
          f"- With the judge also GOOD: {cl['deflected_assertions_and_judge']} tickets; ${cl['cost_per_deflected_judge_usd']} each",
          f"- Model tickets: {cl['llm_tickets']}; mean {cl['mean_tokens_per_llm_ticket']} tokens each; "
          f"latency p50 {cl['p50_latency_s']} s, p95 {cl['p95_latency_s']} s (first ticket, which pays the cold start: {cl['first_ticket_latency_s']} s)",
          f"- Free-tier ceiling: {settings.get('provider.tpm'):,} tokens per minute / {cl['mean_tokens_per_llm_ticket']} = **{cl['tpm_ceiling_tickets_per_min']} tickets per minute**"]
    cache = s.get("llm_cache") or {}
    calls = (cache.get("hits") or 0) + (cache.get("misses") or 0)
    if cache.get("hits"):
        L.append(f"- **Latency caveat:** {cache['hits']} of {calls} model calls in this run were served from the response cache, "
                 "so the latency figures above are NOT representative (cost uses the original token counts and is unaffected). "
                 "Use an uncached run for latency.")
    L.append("")

    L += ["## Judge", ""]
    for title, j in (("Primary", jg), ("Second opinion", s.get("judge_alt"))):
        if not j:
            continue
        ag = j["agreement"]
        L += [f"- **{title}:** rubric `{j['version']}` on {j['model']} (agent is a different family). Judged answers: {j['n']}"
              f" (GOOD {j['good']}, NOT_GOOD {j['not_good']}, error {j['error']})"]
        if ag.get("n"):
            L += [f"  - Agreement with human labels: **{ag['agree']}/{ag['n']} = {ag['agreement']:.0%}** (target {human_labels.agreement_target():.0%},"
                  f" at least {human_labels.min_labels()} labels); labeler: {ag.get('labeler')} ({ag.get('queue_experience')})."
                  f" Judge GOOD where the human said NOT_GOOD: {ag['judge_good_human_not_good']}. Status: {ag['status']}"]
        else:
            L += [f"  - **Agreement with human labels: NOT MEASURED** ({ag.get('status')}). A person labels the replies on the"
                  " admin page /label; then `python -m tier1 eval --rescore <tag>`. Until then no agreement number may be quoted."]
    if str(jg.get("version", "")).startswith("week6"):
        from evaluation.integrated.judge import week6_human_agreement
        L += [f"- The primary rubric is the Week 6 v2 judge (catalog prompt judge.week6_v2; Week 6 agreement with people: {week6_human_agreement()}"
              " on Week 6 replies). That number does not carry over: the Week 6 model is no longer available on this key, and"
              " integrated replies also rest on account facts, which are added as one context block."]
    L.append("")
    L += ["", "## Assertion pass rates", "", "| Check | Passed | n |", "|---|---|---|"]
    for name, v in s["by_check"].items():
        L.append(f"| {name} | {v['passed']} | {v['n']} |")

    L += ["", "## Failed cases", ""]
    failed_rows = [r for r in rows if not r["passed"]]
    for r in failed_rows:
        L.append(f"- **{r['case_id']}** ({r['slice']}), decision {r['decision']}, trace `{r['trace_id']}`: "
                 + "; ".join(f"{c['name']} ({c['detail']})" for c in r["failed_checks"]))
    if not failed_rows:
        L.append("- none")

    L += ["", "## What this suite does NOT cover", ""] + [f"- {t}" for t in not_covered()]
    return "\n".join(L) + "\n"


def write_label_sheet(rows: list[dict]) -> None:
    """For a human. No judge verdicts and no assertion results: those would anchor the labeler."""
    answered = [r for r in rows if r["decision"] == "ANSWER" and r["reply"]]
    lines = ["# Label sheet", "",
             "Label these replies on the admin page /label (it stores each label with the reply it was given for).",
             "GOOD means a Tier-1 lead would send it as written: correct for THIS customer's policy and order, nothing invented,",
             "answers the question, no promise that a refund has been issued. Judge by what an agent who works this queue would do.", ""]
    for r in answered:
        facts = r["entitlement"] or "(no entitlement check was made)"
        lines += [f"## {r['case_id']}", "", f"Account facts: `{facts}`", "", "Reply:", "", f"> {r['reply']}", "",
                  "Sources the assistant had: " + ", ".join(f"`{s['chunk_id']}`" for s in r["sources"]), ""]
    (OUT_DIR / "label_sheet.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tier1 eval")
    ap.add_argument("--tag", default="after")
    ap.add_argument("--only", help="run one slice, e.g. both_versions")
    ap.add_argument("--cases", choices=["main", "holdout", "regression"], default="main",
                    help="holdout = tickets the fixes were not derived from; regression = cases created from reported failures")
    ap.add_argument("--case-id", action="append", help="run only this case id (repeatable)")
    ap.add_argument("--resume", action="store_true", help="continue the run with this tag that a usage cap stopped")
    ap.add_argument("--rescore", metavar="TAG", help="recompute summary, agreement and report from saved results; no model calls")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--ablate", default="", help="comma list: version_filter,policy_guard (before/after runs)")
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.rescore:
        return rescore(args.rescore)
    if args.ablate:
        os.environ["TIER1_ABLATE"] = args.ablate          # inherited by the MCP server processes
    cases = load_cases(args.only, args.limit, args.cases, args.case_id)
    if not cases:
        print("no cases match", file=sys.stderr)
        return 2
    meta = {"ablate": args.ablate, "cases": args.cases, "only": args.only, "limit": args.limit,
            "case_id": args.case_id, "judge": not args.no_judge}
    done: list[dict] = []
    if args.resume:
        stopped = eval_store.run(args.tag)
        if not stopped or stopped["status"] != "partial":
            print(f"nothing to resume: there is no stopped run tagged {args.tag}", file=sys.stderr)
            return 2
        saved = stopped["settings"] or None
        if saved is not None and saved != meta:
            print(f"refusing to resume: this run's settings {meta} differ from the stopped run's {saved}", file=sys.stderr)
            return 2
        done = eval_store.results(args.tag)
        print(f"resuming {args.tag}: {len(done)} cases already finished", flush=True)
    print(f"integrated eval: {len(cases)} cases, tag={args.tag}, ablate={args.ablate or 'none'}, "
          f"judge={'off' if args.no_judge else 'on'}\n", flush=True)

    from src.generation import gateway
    started = time.time()
    try:
        rows = run_cases(cases, judge=not args.no_judge, done=done)
    except RateLimitAbort as stop:
        eval_store.save_run(args.tag, args.cases, "partial", {}, meta, stop.done)
        print(f"\nSTOPPED at {stop.at_case}: the provider's usage cap was reached ({stop.detail}).\n"
              f"{len(stop.done)} cases finished and are saved (run {args.tag}, status partial); no summary or report was written, "
              "because the remaining cases would measure the cap rather than the system. Rerun when the limit resets "
              f"with:  python -m tier1 eval --tag {args.tag} --resume  (same flags as this run).")
        return 3
    summary = summarise(cases, rows, args.tag, args.ablate)
    summary["llm_cache"] = {"hits": gateway.stats["hits"], "misses": gateway.stats["misses"]}
    summary["wall_seconds"] = round(time.time() - started)
    summary["resumed_from_partial"] = len(done)
    summary["settings"] = meta

    eval_store.save_run(args.tag, args.cases, "complete", summary, meta, rows)
    (OUT_DIR / f"results_{args.tag}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    (OUT_DIR / f"summary_{args.tag}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (OUT_DIR / f"report_{args.tag}.md").write_text(render_report(summary, rows), encoding="utf-8")
    if not (args.only or args.limit or args.case_id) and args.cases == "main":
        write_label_sheet(rows)                     # only a full run defines what a person should label
    print(f"\npassed {summary['passed']}/{summary['n']}  |  report: {OUT_DIR / f'report_{args.tag}.md'}")
    return 0


def rescore(tag: str) -> int:
    """Recompute everything derived from saved rows: after labelling, or after a metric changes. No model calls."""
    saved = eval_store.run(tag)
    rows = eval_store.results(tag) if saved else []
    if not rows:
        print(f"no results for tag {tag}", file=sys.stderr)
        return 2
    ids = [r["case_id"] for r in rows]
    every = {c["case_id"]: c for suite in eval_store.TIER1_SUITES for c in eval_store.cases(suite, include_inactive=True)}
    missing = [i for i in ids if i not in every]
    if missing:
        print(f"cannot rescore: case definitions not found for {missing}", file=sys.stderr)
        return 2
    old = saved["summary"] or {}
    summary = summarise([every[i] for i in ids], rows, tag, old.get("ablate") or "")
    for k in ("llm_cache", "wall_seconds", "resumed_from_partial", "settings"):
        if k in old:
            summary[k] = old[k]
    summary["rescored"] = True
    eval_store.save_run(tag, saved["suite"], "complete", summary, saved["settings"], rows)
    (OUT_DIR / f"summary_{tag}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (OUT_DIR / f"report_{tag}.md").write_text(render_report(summary, rows), encoding="utf-8")
    ag = summary["judge"]["agreement"]
    print(f"rescored {tag}: passed {summary['passed']}/{summary['n']}; judge agreement: "
          + (f"{ag['agree']}/{ag['n']} = {ag['agreement']:.0%} ({ag['status']})" if ag.get("n") else f"not measured ({ag.get('status')})"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

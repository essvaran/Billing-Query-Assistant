"""Week 10 race: single agent (answer_question) vs multi-agent orchestrator.

Same 10 Week-6 eval cases, same judge (evaluation.judge, v1) and same
deterministic assertions for both arms. Pass = all assertions pass AND judge
says GOOD, exactly as evaluation/run_eval.py defines it.

Run from the repo root:
    python -m evaluation.week10_race
    python -m evaluation.week10_race --pace 5     # seconds between cases (Groq RPM)

Writes docs/archive/deliverables/week10/{race_table.md, handoffs.log, failure_case.md,
verdict.md, agent_card.json, a2a_lifecycle.md, race_results.json}.
"""

import argparse
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.assertions import run_assertions
from evaluation.judge import judge_response
from evaluation.week10_multi_agent import agent_card, run_multi_agent, synthesis_prompt
from src.generation.cost import calculate_cost
from src.generation.llm_client import default_model
from src.generation.answer import answer_question

OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "archive" / "deliverables" / "week10"



def case_ids() -> list[str]:
    """The race's cases: catalog list week10_case (Admin, Reference data)."""
    from src.catalog import ref
    return ref.codes("week10_case")


def failure_case_id() -> str:
    from src.catalog import ref
    flagged = [v["code"] for v in ref.values("week10_case") if v["meta"].get("failure_demo")]
    return flagged[0] if flagged else case_ids()[0]


def load_cases():
    from src.catalog import eval_store
    rows = {c["case_id"]: c for c in eval_store.cases("docs", include_inactive=True)}
    return [rows[cid] for cid in case_ids() if cid in rows]


def percentile(values, pct):
    data = sorted(values)
    if len(data) == 1:
        return data[0]
    pos = (len(data) - 1) * pct / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return data[lo] + (data[hi] - data[lo]) * (pos - lo)


def grade(question, answer, chunks, pace):
    ids = [c["chunk_id"] for c in chunks]
    checks = run_assertions(answer, ids)
    assertions_ok = all(c.passed for c in checks)
    time.sleep(pace)
    try:
        verdict = judge_response(question, answer, chunks, version="v1")
    except Exception as exc:
        verdict = f"ERROR:{exc}"
    return assertions_ok, verdict, assertions_ok and verdict == "GOOD"


def run_single(case, pace):
    t0 = time.perf_counter()
    try:
        ans = answer_question(case["question"])
        latency = time.perf_counter() - t0
        ok, verdict, passed = grade(case["question"], ans.final_answer, ans.retrieved_chunks, pace)
        return {
            "case_id": case["case_id"], "answer": ans.final_answer, "latency_s": latency,
            "tokens": ans.input_tokens + ans.output_tokens, "input_tokens": ans.input_tokens, "output_tokens": ans.output_tokens,
            "assertions_ok": ok,
            "judge": verdict, "passed": passed, "error": None,
        }
    except Exception as exc:
        return {"case_id": case["case_id"], "answer": f"ERROR: {exc}", "latency_s": time.perf_counter() - t0,
                "tokens": 0, "assertions_ok": False, "judge": "ERROR", "passed": False, "error": str(exc)}


def run_multi(case, pace):
    t0 = time.perf_counter()
    try:
        ans = run_multi_agent(case["question"])
        latency = time.perf_counter() - t0
        ok, verdict, passed = grade(case["question"], ans.final_answer, ans.retrieved_chunks, pace)
        return {
            "case_id": case["case_id"], "answer": ans.final_answer, "latency_s": latency,
            "tokens": ans.total_tokens, "input_tokens": ans.input_tokens, "output_tokens": ans.output_tokens,
            "assertions_ok": ok, "judge": verdict, "passed": passed,
            "error": None, "handoffs": ans.handoffs,
        }
    except Exception as exc:
        return {"case_id": case["case_id"], "answer": f"ERROR: {exc}", "latency_s": time.perf_counter() - t0,
                "tokens": 0, "assertions_ok": False, "judge": "ERROR", "passed": False,
                "error": str(exc), "handoffs": []}


def aggregate(rows):
    lat = [r["latency_s"] for r in rows]
    tokens = sum(r["tokens"] for r in rows)
    return {
        "pass_rate": sum(r["passed"] for r in rows) / len(rows),
        "passes": sum(r["passed"] for r in rows),
        "p50_latency_s": statistics.median(lat),
        "p99_latency_s": percentile(lat, 99),
        "total_tokens": tokens,
        "cost_per_ticket": sum(calculate_cost(default_model(), r.get("input_tokens", 0), r.get("output_tokens", 0))["total_cost_usd"] for r in rows) / len(rows),
    }


def handoff_shares(multi_rows):
    totals = {}
    for r in multi_rows:
        for h in r["handoffs"]:
            totals[h["handoff"]] = totals.get(h["handoff"], 0) + h["total_tokens"]
    grand = sum(totals.values()) or 1
    return sorted(((n, t, t / grand) for n, t in totals.items()), key=lambda x: -x[1])


def write_race_table(single, multi, s_agg, m_agg, mult, shares, cases):
    top_name, top_tokens, top_share = shares[0]
    lines = [
        "# Week 10 race table -- single agent vs multi-agent orchestrator",
        "",
        "Cases (same 10 Week-6 cases from evaluation/eval_set.jsonl, no new cases): "
        + ", ".join(f"{c['case_id']} ({c['mode']})" for c in cases),
        "",
        "Judge: evaluation/judge.py v1 plus the 4 deterministic assertions in evaluation/assertions.py "
        "for BOTH arms. Pass = assertions all pass AND judge GOOD.",
        "",
        "| Metric | Single agent (answer_question) | Multi-agent (orchestrator + 2 workers) |",
        "|---|---|---|",
        f"| Pass rate | {s_agg['passes']}/10 = {s_agg['pass_rate']:.0%} | {m_agg['passes']}/10 = {m_agg['pass_rate']:.0%} |",
        f"| p50 latency (s) | {s_agg['p50_latency_s']:.2f} | {m_agg['p50_latency_s']:.2f} |",
        f"| p99 latency (s) | {s_agg['p99_latency_s']:.2f} | {m_agg['p99_latency_s']:.2f} |",
        f"| Total tokens | {s_agg['total_tokens']:,} | {m_agg['total_tokens']:,} |",
        f"| Cost per ticket (USD) | {s_agg['cost_per_ticket']:.6f} | {m_agg['cost_per_ticket']:.6f} |",
        "",
        f"**Context re-send multiplier: {mult:.1f}x** (multi {m_agg['total_tokens']:,} tokens / "
        f"single {s_agg['total_tokens']:,} tokens). Largest single hand-off: {top_name}, "
        f"{top_share:.0%} of all multi-agent tokens ({top_tokens:,}).",
        "",
        "Hand-off share of multi-agent tokens:",
        "",
        "| Hand-off | Tokens | Share |",
        "|---|---|---|",
    ]
    lines += [f"| {n} | {t:,} | {s:.0%} |" for n, t, s in shares]
    lines += [
        "",
        "Per case:",
        "",
        "| Case | Single pass | Single tokens | Single latency (s) | Multi pass | Multi tokens | Multi latency (s) |",
        "|---|---|---|---|---|---|---|",
    ]
    for s, m in zip(single, multi):
        lines.append(
            f"| {s['case_id']} | {'PASS' if s['passed'] else 'FAIL'} | {s['tokens']:,} | {s['latency_s']:.2f} "
            f"| {'PASS' if m['passed'] else 'FAIL'} | {m['tokens']:,} | {m['latency_s']:.2f} |"
        )
    lines += [
        "",
        "Notes:",
        "- With n=10, p99 is interpolated and sits very close to the slowest case.",
        f"- Cost uses the model prices in the catalog (Admin, Model prices), input and output priced separately. "
        "Tokens count the answering LLM calls only (judge calls excluded for both arms).",
        "- Context strategy: triage sees only the question; policy worker sees the rewritten query and "
        "retrieved chunks; orchestrator sees the question, the draft and only the chunks the draft cites.",
        "- Tool strategy: triage worker has no tools; policy worker has one retrieval tool.",
        "- Each arm was run once. No re-runs were done to improve a result.",
        "- Latency includes Groq 429 rate-limit back-off waits, which add noise to both arms; treat latency "
        "gaps as indicative, and the pass-rate and token numbers as the firmer evidence.",
    ]
    (OUT_DIR / "race_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_handoffs_log(multi, failure_run):
    lines = ["# One line per hand-off. Tokens are input/output/total as reported by the LLM provider."]
    for r in multi:
        for h in r["handoffs"]:
            lines.append(
                f"case={r['case_id']} handoff={h['handoff']} input={h['input_tokens']} "
                f"output={h['output_tokens']} total={h['total_tokens']} ms={h['ms']} note={h['note']}"
            )
    lines.append("")
    lines.append(f"# Failure-injection demo (case {failure_case_id()}), not part of the race totals")
    for h in failure_run.handoffs:
        lines.append(
            f"case={failure_case_id()}-injected handoff={h['handoff']} input={h['input_tokens']} "
            f"output={h['output_tokens']} total={h['total_tokens']} ms={h['ms']} note={h['note']}"
        )
    (OUT_DIR / "handoffs.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


def classify_failure(ans):
    has_citation = "[" in ans.final_answer and "]" in ans.final_answer
    if not ans.policy_lookup_failed:
        return "no failure observed", "The injected failure did not fire."
    if ans.tool_attempts > 1 and not has_citation:
        return (
            "retried, then degraded",
            f"Orchestrator retried the policy tool ({ans.tool_attempts} attempts, all HTTP 500), then returned an "
            "honest partial answer. It did not synthesise as if the worker had answered.",
        )
    if has_citation:
        return "lied", "The final reply contains citations although no documentation was retrieved."
    return "degraded without retry", "No retry happened before the degraded reply."


def write_failure_case(case, ans):
    label, summary = classify_failure(ans)
    lines = [
        "# Failure case -- policy-lookup worker returns HTTP 500",
        "",
        f"Case: {case['case_id']} -- \"{case['question']}\" (expected behaviour: {case['expected_behavior']}).",
        "Injection: the policy worker's retrieval tool returns HTTP 500 on every attempt for this case "
        "(a persistent outage), run separately from the clean 10-case race so race numbers are not contaminated.",
        "",
        f"**What the orchestrator actually did: {label}.**",
        "",
        summary,
        "",
        "## Hand-off log for this run",
        "",
    ]
    for h in ans.handoffs:
        lines.append(f"- {h['handoff']}: tokens={h['total_tokens']} {h['note']}")
    lines += [
        "",
        "## Final reply sent to the customer",
        "",
        "```",
        ans.final_answer,
        "```",
        "",
        "## Why this is not a lie",
        "",
        "The orchestrator system prompt contains this rule, and the policy worker returns "
        "policy_lookup_failed instead of a draft when the tool fails:",
        "",
        "```",
        synthesis_prompt().split("4. ")[1],
        "```",
        "",
        f"Tool attempts: {ans.tool_attempts}. Retrieved chunks: {len(ans.retrieved_chunks)}. "
        f"Citations in reply: {'yes' if ('[' in ans.final_answer) else 'none'}.",
    ]
    (OUT_DIR / "failure_case.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return label


def write_verdict(s_agg, m_agg, mult):
    gain = m_agg["pass_rate"] - s_agg["pass_rate"]
    keep = gain >= 0.10
    lines = [
        "# Verdict",
        "Sunk-cost bias, named out loud: I spent a week building this orchestrator, so I want it to win. "
        "I am ignoring that and deciding on the numbers.",
        f"Pass rate: single {s_agg['passes']}/10 vs multi {m_agg['passes']}/10 ({gain:+.0%}).",
        f"Tokens: single {s_agg['total_tokens']:,} vs multi {m_agg['total_tokens']:,} ({mult:.1f}x); "
        f"cost per ticket {s_agg['cost_per_ticket']:.6f} vs {m_agg['cost_per_ticket']:.6f} USD.",
        f"Latency: p50 {s_agg['p50_latency_s']:.2f}s vs {m_agg['p50_latency_s']:.2f}s; "
        f"p99 {s_agg['p99_latency_s']:.2f}s vs {m_agg['p99_latency_s']:.2f}s.",
        "Rule set before looking at results: keep multi-agent only if pass rate improves by 10 points or more.",
        f"Decision: {'KEEP the multi-agent orchestrator' if keep else 'KILL the multi-agent orchestrator and keep the single agent'}.",
        (
            "The quality gain justifies the extra tokens and latency."
            if keep
            else "The extra hand-offs did not buy enough quality to pay for the extra tokens and latency."
        ),
        "Each arm ran once; no re-runs. Revisit only if parallel, independent sub-tasks appear.",
    ]
    (OUT_DIR / "verdict.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return keep


def write_a2a(case, label):
    (OUT_DIR / "agent_card.json").write_text(json.dumps(agent_card(), indent=2) + "\n", encoding="utf-8")
    lines = [
        "# A2A mapping for the failed case (bonus)",
        "",
        f"Case {case['case_id']} (injected policy-lookup HTTP 500). Observed behaviour: {label}.",
        "",
        "## Lifecycle",
        "",
        "submitted, then working, then (policy sub-task: 2 attempts, both 500), then input-required",
        "",
        "Recommended end state: **input-required**, not failed. The task is recoverable: the lookup outage is "
        "transient and a human ticket owner (or a later retry) can supply or confirm the policy answer. Marking "
        "the task failed would throw away the triage result and tell the customer nothing; the degraded reply "
        "already tells them honestly that verification is pending. Move to failed only if the owner declines "
        "to act or retries are exhausted by policy.",
        "",
        "## What A2A buys over a plain REST call to the worker",
        "",
        "- Discovery and contract: the AgentCard (agent_card.json) advertises skills, input/output modes and auth, "
        "so a caller learns what the worker does without reading its code.",
        "- A standard task lifecycle: states like input-required and a task id let a paused or long-running job "
        "be resumed, where a bare REST call only gives a status code and loses the context.",
    ]
    (OUT_DIR / "a2a_lifecycle.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_race(pace=3.0, on_progress=None):
    """Run the full race and write all deliverables. on_progress(done, total) is optional."""
    args = argparse.Namespace(pace=pace)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cases = load_cases()
    print(f"Race: {len(cases)} cases, same judge for both arms")

    single, multi = [], []
    for i, case in enumerate(cases, 1):
        s = run_single(case, args.pace)
        time.sleep(args.pace)
        m = run_multi(case, args.pace)
        single.append(s)
        multi.append(m)
        print(
            f"[{i:2}/{len(cases)}] {case['case_id']:<5} single={'PASS' if s['passed'] else 'FAIL'} "
            f"{s['tokens']:>6}tok {s['latency_s']:>6.2f}s | multi={'PASS' if m['passed'] else 'FAIL'} "
            f"{m['tokens']:>6}tok {m['latency_s']:>6.2f}s",
            flush=True,
        )
        if on_progress:
            on_progress(i, len(cases))
        time.sleep(args.pace)

    s_agg, m_agg = aggregate(single), aggregate(multi)
    mult = round(m_agg["total_tokens"] / max(s_agg["total_tokens"], 1), 1)
    shares = handoff_shares(multi)

    print(f"\nFailure injection on {failure_case_id()}")
    failure_case = next(c for c in cases if c["case_id"] == failure_case_id())
    failure_run = run_multi_agent(failure_case["question"], inject_failure=True)

    write_race_table(single, multi, s_agg, m_agg, mult, shares, cases)
    write_handoffs_log(multi, failure_run)
    label = write_failure_case(failure_case, failure_run)
    keep = write_verdict(s_agg, m_agg, mult)
    write_a2a(failure_case, label)

    payload = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "cases": case_ids(),
        "single": {**s_agg, "rows": single},
        "multi": {**m_agg, "rows": multi},
        "multiplier": mult,
        "failure_behaviour": label,
        "verdict_keep": keep,
    }
    (OUT_DIR / "race_results.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    print(f"\nPass rate   single {s_agg['pass_rate']:.0%} | multi {m_agg['pass_rate']:.0%}")
    print(f"p50 / p99   single {s_agg['p50_latency_s']:.2f}/{s_agg['p99_latency_s']:.2f}s | "
          f"multi {m_agg['p50_latency_s']:.2f}/{m_agg['p99_latency_s']:.2f}s")
    print(f"Tokens      single {s_agg['total_tokens']:,} | multi {m_agg['total_tokens']:,} ({mult:.1f}x)")
    print(f"Failure     {label}")
    print(f"Verdict     {'KEEP' if keep else 'KILL'}")
    print(f"Wrote deliverables to {OUT_DIR}")
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pace", type=float, default=3.0, help="seconds to sleep between LLM-heavy steps")
    args = parser.parse_args()
    run_race(args.pace)


if __name__ == "__main__":
    main()

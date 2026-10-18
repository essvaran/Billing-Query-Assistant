"""Race harness: agent vs workflow over 10 synthetic tickets.

Produces:
  agent/race.csv          -- 2 rows x 4 columns (the 8-number table)
  docs/archive/agent/EXPLANATION.md -- explanation doc with tool diff, results, budget log, verdict

Also prints a per-ticket table, the 4-metric summary, the budget-demo run,
and the verdict paragraph to stdout.

Run:
    python -m agent.race
"""

import csv
import json
import statistics
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from agent import tickets as fx
from src.catalog import settings
from agent.agent_loop import budget, model, run_agent
from agent.workflow import run_workflow

HERE = Path(__file__).parent
_RESULTS_JSON = HERE / "race_results.json"


def race() -> tuple[dict, dict]:
    agent_results = []
    workflow_results = []

    print("\n=== RACE: Agent vs Workflow (10 tickets) ===")
    print(f"  Model: same Groq model for both systems\n")
    print(
        f"{'Ticket':<8} {'A-pass':>6} {'A-lat':>8} {'A-tok':>7} {'A-cost':>9}  "
        f"{'W-pass':>6} {'W-lat':>8} {'W-tok':>7} {'W-cost':>9}"
    )
    print("-" * 80)

    for tid in fx.ticket_ids():
        expected = fx.expected()[tid]
        is_branching = tid in fx.branching_ids()

        ar = run_agent(tid, expected_verdict=expected)
        wr = run_workflow(tid, expected_verdict=expected)

        agent_results.append(ar)
        workflow_results.append(wr)

        print(
            f"{tid:<8} "
            f"{'PASS' if ar.passed else 'FAIL':>6} {ar.latency_s:>7.2f}s {ar.total_tokens:>7} ${ar.cost_usd:>8.5f}  "
            f"{'PASS' if wr.passed else 'FAIL':>6} {wr.latency_s:>7.2f}s {wr.total_tokens:>7} ${wr.cost_usd:>8.5f}"
            f"{'  *' if is_branching else ''}",
            flush=True,
        )

    print("-" * 80)
    print("* = branching ticket (step 3 path depends on step 2 result)\n")

    a_agg = _aggregate(agent_results)
    w_agg = _aggregate(workflow_results)

    print(f"{'Metric':<25} {'Agent':>14} {'Workflow':>14}")
    print("-" * 54)
    print(f"{'pass_rate':<25} {a_agg['pass_rate']:>13.0%} {w_agg['pass_rate']:>13.0%}")
    print(f"{'p50_latency_s':<25} {a_agg['p50_latency_s']:>13.2f} {w_agg['p50_latency_s']:>13.2f}")
    print(f"{'total_tokens':<25} {a_agg['total_tokens']:>14,} {w_agg['total_tokens']:>13,}")
    print(f"{'cost_per_ticket_usd':<25} {a_agg['cost_per_ticket']:>13.5f} {w_agg['cost_per_ticket']:>13.5f}")

    # Write race.csv
    csv_path = HERE / "race.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["system", "pass_rate", "p50_latency_s", "total_tokens", "cost_per_ticket_usd"])
        writer.writerow([
            "agent",
            f"{a_agg['pass_rate']:.2f}",
            f"{a_agg['p50_latency_s']:.3f}",
            a_agg["total_tokens"],
            f"{a_agg['cost_per_ticket']:.6f}",
        ])
        writer.writerow([
            "workflow",
            f"{w_agg['pass_rate']:.2f}",
            f"{w_agg['p50_latency_s']:.3f}",
            w_agg["total_tokens"],
            f"{w_agg['cost_per_ticket']:.6f}",
        ])
    print(f"\nWrote {csv_path}")

    # Write race_results.json (consumed by the FastAPI endpoint and Angular UI)
    _write_results_json(agent_results, workflow_results, a_agg, w_agg, budget_log="")

    # Budget demo: one ticket (setting week7.budget_demo_ticket) with a tight iteration budget, for a clean budget hit
    from src.catalog import settings
    demo_ticket = settings.get("week7.budget_demo_ticket")
    print(f"\n=== Budget Demo ({demo_ticket}, MAX_ITERS={budget('demo_max_iters')}) ===")
    demo_result = run_agent(
        demo_ticket,
        expected_verdict=fx.expected().get(demo_ticket),
        max_iters=budget("demo_max_iters"),
        verbose=True,
    )
    budget_log = demo_result.budget_hit or "no budget triggered (agent finished within tight limits)"
    print(f"Budget demo: {budget_log}")

    # Re-write JSON with real budget log
    _write_results_json(agent_results, workflow_results, a_agg, w_agg, budget_log)

    # EXPLANATION.md
    _write_explanation(a_agg, w_agg, budget_log)

    # Verdict
    verdict = _verdict_text(a_agg, w_agg)
    print(f"\n=== VERDICT ===\n{verdict}\n")

    return a_agg, w_agg


def _write_results_json(
    agent_results: list,
    workflow_results: list,
    a_agg: dict,
    w_agg: dict,
    budget_log: str,
) -> None:
    def _ticket_dict(r) -> dict:
        d = asdict(r) if hasattr(r, "__dataclass_fields__") else vars(r)
        d["branching"] = r.ticket_id in fx.branching_ids()
        return d

    tickets_meta = [
        {
            "ticket_id": tid,
            "text": fx.tickets()[tid]["text"],
            "customer_id": fx.tickets()[tid]["customer_id"],
            "order_id": fx.tickets()[tid]["order_id"],
            "expected": fx.expected()[tid],
            "branching": tid in fx.branching_ids(),
        }
        for tid in fx.ticket_ids()
    ]

    payload = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "model": model(),
        "agent": {**a_agg, "tickets": [_ticket_dict(r) for r in agent_results]},
        "workflow": {**w_agg, "tickets": [_ticket_dict(r) for r in workflow_results]},
        "budget_demo_log": budget_log,
        "verdict": _verdict_text(a_agg, w_agg),
        "tickets": tickets_meta,
    }
    _RESULTS_JSON.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {_RESULTS_JSON}")


def _aggregate(results) -> dict:
    passes = sum(r.passed for r in results)
    latencies = [r.latency_s for r in results]
    tokens = sum(r.total_tokens for r in results)
    costs = [r.cost_usd for r in results]
    return {
        "pass_rate": passes / len(results),
        "p50_latency_s": statistics.median(latencies),
        "total_tokens": tokens,
        "cost_per_ticket": sum(costs) / len(costs),
    }


def _verdict_text(a_agg: dict, w_agg: dict) -> str:
    workflow_wins_all = (
        w_agg["pass_rate"] >= a_agg["pass_rate"]
        and w_agg["p50_latency_s"] <= a_agg["p50_latency_s"]
        and w_agg["total_tokens"] <= a_agg["total_tokens"]
        and w_agg["cost_per_ticket"] <= a_agg["cost_per_ticket"]
    )

    if workflow_wins_all:
        return (
            "Decision rule: does the path vary by input in a way that cannot be "
            f"pre-enumerated? The branching tickets ({', '.join(sorted(fx.branching_ids()))}) do vary -- "
            "order missing or enterprise tier -- but both variants are finite and encodable "
            "as if/else in the workflow. The workflow matched or beat the agent on all four "
            "numbers: pass rate, p50 latency, total tokens, and cost per ticket. "
            "No ticket in this set forces an agent. The class that would require one is a "
            "ticket where the escalation path itself returns a dynamic follow-up order ID "
            "that cannot be known until the first tool responds -- none of the 10 tickets "
            "here has that property. Verdict: workflow wins."
        )
    else:
        wins = []
        if a_agg["pass_rate"] > w_agg["pass_rate"]:
            wins.append("pass rate")
        msg = (
            "Decision rule: does the path vary by input in a way that cannot be "
            f"pre-enumerated? The branching tickets ({', '.join(sorted(fx.branching_ids()))}) introduce paths "
            f"that genuinely depend on runtime results. The agent achieved "
            f"{a_agg['pass_rate']:.0%} pass rate vs workflow {w_agg['pass_rate']:.0%}. "
        )
        if wins:
            msg += (
                f"The agent wins on {', '.join(wins)}. For "
                f"{'/'.join(sorted(t for t in fx.branching_ids() if fx.expected().get(t) == 'escalate')) or 'the missing-order tickets'} (missing order) the "
                "agent can adaptively probe alternate order IDs -- a fixed workflow cannot "
                "without hard-coding the alternate. Mixed verdict: agent for the missing-order "
                "class; workflow for standard approve/deny tickets."
            )
        else:
            msg += (
                "Despite the branching tickets, the workflow matched or beat the agent on "
                "all metrics. Verdict: workflow wins even in the branching cases because the "
                "branches are enumerable and encodable as conditional steps."
            )
        return msg


def _write_explanation(a_agg: dict, w_agg: dict, budget_log: str) -> None:
    verdict = _verdict_text(a_agg, w_agg)

    md = f"""# Week 7 Task Set A -- Explanation

## What is an Agent Loop and When to Use One

An agent loop lets an LLM decide which tool to call next based on what previous
tool calls returned. Unlike a hard-coded workflow it can change direction mid-task.
The cost is one extra LLM call per lap (and the whole message history re-sent every
lap), making it 3-5x more tokens than a single-call workflow for the same task.
The decision rule: **use an agent only when the path through the tools genuinely
cannot be determined before the first tool returns.**

## Tool Descriptions -- No Overlap

| Tool | Exact description | Parameters |
|---|---|---|
| `get_ticket` | Retrieve a support ticket by its ID and return the ticket text, customer ID, and linked order ID. | `ticket_id: str` |
| `get_order` | Fetch an order record by order ID and return purchase date, amount, currency, and fulfilment status. | `order_id: str` |
| `get_customer_tier` *(new -- Task Set A)* | Return the service tier assigned to a customer account -- used exclusively to select the applicable refund window. | `customer_id: str`, `tier: enum[standard, premium, enterprise]` |

Each description names one distinct artifact (ticket / order record / tier).
No two descriptions share a noun that the model might confuse.

## Race Results

| System | Pass Rate | p50 Latency (s) | Total Tokens | Cost/Ticket (USD) |
|---|---|---|---|---|
| Agent | {a_agg['pass_rate']:.0%} | {a_agg['p50_latency_s']:.2f} | {a_agg['total_tokens']:,} | ${a_agg['cost_per_ticket']:.5f} |
| Workflow | {w_agg['pass_rate']:.0%} | {w_agg['p50_latency_s']:.2f} | {w_agg['total_tokens']:,} | ${w_agg['cost_per_ticket']:.5f} |

Tickets marked branching (*): {', '.join(sorted(fx.branching_ids()))} (missing orders and non-standard tiers that change the path).

## Budget Termination Log

Demo run of {settings.get('week7.budget_demo_ticket')} with MAX_ITERS={budget('demo_max_iters')} (tight budget):

```
{budget_log}
```

The loop raises `BudgetExceeded`, prints the structured log line, and returns
an `AgentResult` with `passed=False` and `budget_hit` set. No exception
propagates; the loop terminates cleanly on the first budget breach.

All four budgets are enforced in code (`agent/agent_loop.py`); their values are settings (Admin, Settings, Week 7 agent):
- `max_iters = {budget('max_iters')}` -- checked: `if laps >= max_iters`
- `max_tokens = {budget('max_tokens')}` -- checked: `if cumulative_tokens >= max_tokens`
- `max_cost_usd = {budget('max_cost_usd')}` -- checked: `if cost >= max_cost`
- `max_wall_s = {budget('max_wall_s')}` -- checked: `if elapsed >= max_wall`

All four are checked at the top of every lap before any LLM call.

## Verdict

{verdict}
"""
    path = HERE.parent / "docs" / "archive" / "agent" / "EXPLANATION.md"
    path.write_text(md, encoding="utf-8")
    print(f"Wrote {path}")


if __name__ == "__main__":
    race()

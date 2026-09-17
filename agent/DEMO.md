# Week 7 Task Set A -- Demo Guide

A step-by-step walkthrough of every runnable command. Follow these in order to
reproduce all submission deliverables from scratch.

---

## Prerequisites

1. `GROQ_API_KEY` must be set in `.env` at the project root. Verify:
   ```bash
   python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('GROQ_API_KEY','NOT SET')[:10])"
   ```
2. Run all commands from the project root (`E:\Python\Project\rag-billing-support\`).
3. The virtual environment must be active (`.venv\Scripts\activate` on Windows).

---

## Step 1 -- Single Agent Run (normal ticket, in-window)

```bash
python -m agent.agent_loop T001
```

**What to look for:**
- `[lap 1]` -- agent calls `get_ticket` to retrieve the ticket details
- `[lap 2]` -- agent calls `get_order` + `get_customer_tier` (possibly in one lap)
- `[lap 3]` or final lap -- `finish_reason=stop`, agent drafts an **approve** reply
- Final line: `Pass: True`

**What it proves:** The agent correctly resolves a standard in-window refund
(T001 was purchased 20 days ago, customer has a 30-day window).

---

## Step 2 -- Single Workflow Run (same ticket)

```bash
python -m agent.workflow T001
```

**What to look for:**
- `[step 1]` -- hard-coded call to `get_ticket`
- `[step 2]` -- hard-coded call to `get_order` (order found, 20 days ago)
- `[step 3]` -- hard-coded call to `get_customer_tier` (standard, 30 days)
- `[llm]` -- one LLM call with all facts pre-assembled
- Reply approves the refund, `Pass: True`

**What it proves:** The workflow produces the same correct reply with exactly
1 LLM call instead of 2-3. This is the cost difference that shows up in the race.

---

## Step 3 -- Budget Termination Demo (T008, tight budget)

```bash
python -m agent.agent_loop T008 --tight
```

**What to look for:**

T008 references order O208 which is not in the system. The agent will:
1. Call `get_ticket` -- retrieves ticket T008 (lap 1)
2. Call `get_order("O208")` -- returns `{"error": "not_found"}` (lap 2)
3. **Budget fires** -- `MAX_ITERS=2` (tight mode) is reached before lap 3 runs

You will see:

```
BUDGET_HIT budget=max_iters value=2 limit=2 ticket=T008
```

The agent exits cleanly: `BudgetExceeded` is raised inside the loop, caught,
logged, and an `AgentResult(passed=False, budget_hit=...)` is returned.
No exception propagates to the caller.

**What it proves (rubric item):** All four budgets are enforced in code.
The `--tight` flag sets `max_iters=2`; the other three budgets (tokens,
cost, wall-clock) would fire the same way if their thresholds were reached.

---

## Step 4 -- Full Race (all 10 tickets, both systems)

```bash
python -m agent.race
```

**What to look for:**
- A per-ticket table with PASS/FAIL, latency, tokens, cost for both systems
- `*` on T008, T009, T010 -- these are the three branching tickets
- A 4-metric summary table (pass rate, p50 latency, total tokens, cost/ticket)
- A budget-demo run of T008 with `MAX_ITERS=2` showing the `BUDGET_HIT` log line
- The verdict paragraph (under 150 words)

**What it writes:**
- `agent/race.csv` -- 2 rows x 4 columns (the 8-number table)
- `agent/EXPLANATION.md` -- full explanation doc with verdict

**Expected duration:** 2-4 minutes (20 Groq API calls for the race + demo).

---

## Step 5 -- Inspect the Outputs

### race.csv

```bash
python -c "import csv; [print(r) for r in csv.reader(open('agent/race.csv'))]"
```

| Column | Meaning |
|---|---|
| `system` | `agent` or `workflow` |
| `pass_rate` | Fraction of 10 tickets where the reply contained the correct verdict keyword |
| `p50_latency_s` | Median seconds-per-ticket (50th percentile across all 10) |
| `total_tokens` | Sum of input+output tokens across all 10 tickets |
| `cost_per_ticket_usd` | Average USD cost per ticket (tokens x $0.90/1M) |

### EXPLANATION.md

Open `agent/EXPLANATION.md`. Verify:
- Tool description table shows 3 non-overlapping descriptions
- Race results table matches race.csv
- Budget log shows `BUDGET_HIT`
- Verdict is consistent with the numbers (workflow ahead => verdict says workflow wins)

---

## Step 6 -- Understanding the Verdict

The decision rule taught in Module 4:

> Use an agent **only** when the path through the tools genuinely cannot be
> determined before the first tool returns.

For this ticket set:
- T001-T007: approve or deny based on days vs window -- path known at design time
- T008-T009: order not found -- escalate path, but "if order missing: escalate"
  is encodable as a workflow conditional
- T010: enterprise tier with 60-day window -- again, "if tier==enterprise: use 60d"
  is a static branch

All three branching cases are **finite and enumerable**. The workflow handles
them with simple if/else logic. The agent adds extra laps (and tokens) without
gaining correctness. **The workflow wins on all four numbers.**

The ticket class that would genuinely force an agent: a missing-order case where
the escalation returns a **dynamic secondary order ID** that differs per customer
and cannot be pre-enumerated. None of the 10 tickets here has that property.

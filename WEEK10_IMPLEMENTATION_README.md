# Week 10 Implementation: Multi-Agent Orchestrator vs Single Agent

This document explains everything built for Week 10 Task Set A ("Race the triage
squad against your single agent"), how it works, and how to demo it step by step.
For the plain-English concept guide (orchestrator, workers, A2A, MCP, sunk cost),
read `WEEK10_MULTIAGENT_A2A_README.md` first.

---

## 1. What was asked

Build a manager agent with two specialist workers, race it against the existing
single agent on the same 10 Week-6 eval cases with the same judge, and report:

1. Four numbers for both arms: pass rate, p50 and p99 latency, total tokens, cost per ticket.
2. The context re-send multiplier (multi tokens divided by single tokens) and the
   single largest hand-off.
3. A per-hand-off token log.
4. What the orchestrator does when a worker returns HTTP 500 (retry, degrade, or lie).
5. A keep or kill verdict that names sunk-cost bias.
6. Bonus: an AgentCard and the failed case mapped onto the A2A task lifecycle.

You also asked for a UI under the Admin menu to demonstrate all of it.

---

## 2. Decisions made

| Decision | Choice | Why |
|---|---|---|
| Which "Week 6 eval" | `evaluation/eval_set.jsonl` plus `evaluation/judge.py` (confirmed by you) | It is the real Week 6 harness. The 10-ticket refund set in `agent/tickets.py` belongs to Week 7. |
| Single agent arm | `src/generation/answer.py::answer_question` | Existing RAG pipeline, unchanged. |
| Which 10 cases | R01, R02, G01, G02, F01, F04, A01, A03, CE01, CE04 | The set has 25 cases and the brief says 10 and no new cases. This is a fixed spread across all five modes, no new cases written. |
| Same judge | Judge v1 plus the 4 deterministic assertions for both arms | Pass means all assertions pass AND judge says GOOD, identical to `evaluation/run_eval.py`. |
| Retrieval inside the worker | `hybrid_search` directly, not `agent/tools.py::search_knowledge_base` | That tool truncates chunk text to 300 characters, which would have starved the multi-agent arm and made the race unfair. |
| Cost constant | 0.90 USD per 1M tokens | Same constant used in `agent/agent_loop.py`. |

---

## 3. Architecture

```
Question
   |
   v
Orchestrator (manager)
   |
   +-- 1. Triage worker      no tools, 1 LLM call
   |        rewrites "error 4032" into "What does error code ERR-4032 mean?"
   |        skipped when the question has no code to normalize
   |
   +-- 2. Policy-lookup worker   1 retrieval tool + 1 LLM call
   |        hybrid search (BM25 + dense), retries the tool once on failure,
   |        drafts a cited answer using the same prompt as the single agent
   |
   +-- 3. Orchestrator synthesis   1 LLM call
            checks the draft against the cited chunks, keeps citations
            verbatim, returns the final answer or the standard refusal
```

Context strategy (stated on purpose, so the race tests the pattern and not a careless prompt):

- Triage sees only the question.
- Policy worker sees the rewritten query and the retrieved chunks.
- Orchestrator sees the question, the draft, and only the chunks the draft cites.

Narrow specialists: the triage worker has no tools at all, the policy worker has a
single retrieval tool. Neither has the full tool set.

### Shortcuts and safety rules in the orchestrator

- No chunks retrieved, or the worker already refused: the orchestrator returns the
  standard refusal without a third LLM call (same behaviour as the single agent).
- Final answer with invalid citations: collapses to the standard refusal.
- Policy lookup failed: the worker returns `policy_lookup_failed` and no draft. The
  orchestrator prompt forbids answering from memory and tells it to say lookup is
  unavailable and the question is escalated.

---

## 4. Files added and changed

### New files

| File | Purpose |
|---|---|
| `evaluation/week10_multi_agent.py` | Orchestrator, triage worker, policy worker, `MultiAgentAnswer`, `AGENT_CARD`, failure injection, Langfuse tracing |
| `evaluation/week10_race.py` | Race harness: runs both arms, grades both, aggregates metrics, writes all deliverables. Exposes `run_race()` |
| `api/multiagent_router.py` | Admin-only API: `/api/multiagent/{cases,results,status,run,ask}` |
| `frontend/src/app/services/multiagent.service.ts` | Angular HTTP service and types |
| `frontend/src/app/components/multiagent/` | Angular component (`.ts`, `.html`, `.scss`) for the UI |
| `deliverables/week10/` | Generated outputs (see section 5) |
| `WEEK10_MULTIAGENT_A2A_README.md` | Concept guide |
| `WEEK10_IMPLEMENTATION_README.md` | This file |

### Existing files changed

| File | Change |
|---|---|
| `api/main.py` | Imports and registers `multiagent_router` |
| `frontend/src/app/components/admin/admin.component.ts` | Imports `MultiAgentComponent`, adds the `multiagent` tab type |
| `frontend/src/app/components/admin/admin.component.html` | Adds the "Multi-Agent" tab button and the `<app-multiagent>` outlet |
| `.claude/launch.json` | Adds a `FastAPI` entry (port 8000) next to `Angular Dev` |

No Week 6 or Week 7 file (`answer.py`, `judge.py`, `assertions.py`, `agent/*`) was modified.

---

## 5. Deliverables (generated into `deliverables/week10/`)

| File | Content |
|---|---|
| `race_table.md` | 4 metrics for both arms, named cases, multiplier line, hand-off share table, per-case table, caveats |
| `handoffs.log` | One line per hand-off with input, output and total tokens, time and a note. The failure demo is listed in a separate section |
| `failure_case.md` | The injected HTTP 500, the hand-off log, the final reply, and the one-line classification |
| `verdict.md` | Keep or kill, cites pass rate, tokens, cost and latency, names sunk-cost bias (under 10 lines) |
| `agent_card.json` | Bonus: the orchestrator's AgentCard (skills, input and output modes, auth) |
| `a2a_lifecycle.md` | Bonus: failed case mapped to the A2A lifecycle, plus what A2A buys over plain REST |
| `race_results.json` | Machine-readable results used by the UI |

---

## 6. Results from the recorded run

| Metric | Single agent | Multi-agent |
|---|---|---|
| Pass rate | 8/10 (80%) | 7/10 (70%) |
| p50 latency | 2.21 s | 7.84 s |
| p99 latency | 13.41 s | 19.50 s |
| Total tokens | 12,621 | 18,231 |
| Cost per ticket | $0.001136 | $0.001641 |

- Context re-send multiplier: **1.4x**.
- Largest hand-off: `orchestrator_to_policy_worker`, 54% of all multi-agent tokens (it re-sends the retrieved chunks).
- Injected failure: **retried, then degraded**. Two tool attempts, both HTTP 500, then an honest "lookup unavailable, escalated" reply. It did not invent an answer.
- Verdict: **KILL** the multi-agent orchestrator and keep the single agent. The keep rule was fixed before the run: keep only if pass rate improves by 10 points or more.

Caveats to be honest about:

- Each arm ran once. No re-runs were done to improve a result.
- Latency includes Groq 429 rate-limit back-off waits, so latency gaps are indicative. Pass rate and tokens are the firmer evidence.
- These numbers are from the second run, after the triage change (triage is skipped when the question has no code to normalize). That change fixed CE01, where the rewrite had dropped the chunk holding the fix. R02 failed for multi in this run; its cause was not investigated.
- With n=10, p99 is interpolated and sits very close to the slowest case.
- G01 and G02 (corpus-gap, refusal expected) fail in both arms. That is existing Week 6 behaviour and was not investigated.
- The failure demo runs separately from the 10-case race so it does not contaminate the race numbers.

---

## 7. Setup

Requirements: the repo `.venv`, a `.env` with `GROQ_API_KEY`, `LLM_PROVIDER=groq`, `LLM_MODEL`, the admin and Google settings the app already uses, and the Chroma index already built in `chroma_db/`.

Use the repo's virtual environment, not the system Python (the system Python lacks `dotenv` and `rank_bm25`).

---

## 8. Demo steps

### Option A: command line (no UI)

Step 1. From the repo root, run the full race (about 5 to 8 minutes, Groq rate limits apply):

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m evaluation.week10_race
```

Step 2. Watch the per-case lines and the final summary (pass rate, p50 and p99, tokens, multiplier, failure behaviour, verdict).

Step 3. Open the generated files in `deliverables/week10/`: `race_table.md`, `handoffs.log`, `failure_case.md`, `verdict.md`.

Optional: slow the pace if you hit 429 errors:

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m evaluation.week10_race --pace 5
```

### Option B: the UI under Admin

Step 1. Start the API from the repo root:

```bash
.venv/Scripts/python.exe -m uvicorn api.main:app --port 8000
```

Step 2. Start the Angular dev server (it proxies `/api` to port 8000):

```bash
cd frontend && npx ng serve --port 4200 --proxy-config proxy.conf.json
```

Step 3. Open http://localhost:4200 and sign in with the admin Google account.

Step 4. Click **Admin** in the top bar, then the **Multi-Agent** tab (last tab, after Trajectory).

Step 5. Read the pattern card at the top: orchestrator, triage worker (no tools), policy worker (one tool), plus the MCP vs A2A note.

Step 6. Live demo, normal case:

1. In "Live demo: ask both", pick `F01 (false_refusal): What does ERR-4032 mean?` from the dropdown (it fills the question box).
2. Leave the failure checkbox off and click **Ask both**. The first call is slow (about 40 s) because the embedding model loads once.
3. Compare the two columns: answer, tokens, latency, cost, and the four citation check pills. The multi-agent column shows the token multiplier chip and what triage rewrote the query to.
4. Read the hand-off table: triage, policy worker search, policy worker draft, orchestrator synthesis, with a token bar per row. This is the context re-send cost made visible.

Step 7. Live demo, failure case:

1. Tick **Inject HTTP 500 into the policy-lookup worker** and click **Ask both** again.
2. The multi-agent column shows a **degraded** badge. The hand-off table highlights two failed `policy_worker_search_tool` attempts (attempt 1 retrying, attempt 2 final), then a short synthesis call.
3. The reply says documentation lookup is unavailable and the question was escalated. No made-up answer. This is "retried, then degraded".

Step 8. Race results section (scroll down):

1. Five metric cards for single vs multi with a WIN badge on the better side.
2. The **1.4x** multiplier banner and the bar chart of where multi-agent tokens went (policy worker draft is the largest).
3. Per-case table: click any row to expand both full answers, the judge verdicts and that case's hand-offs.

Step 9. Verdict and failure panels:

1. The verdict card shows KEEP or KILL with the full text (names sunk-cost bias, cites the numbers).
2. The failure card shows the lifecycle steps (submitted, working, policy tool HTTP 500 twice, input-required), the observed behaviour and the full failure write-up.

Step 10. Optional: click **Run Race (10 cases)** to regenerate everything from the UI. A progress bar shows cases done out of 10, and the results refresh when it finishes.

Note: the AgentCard and the A2A lifecycle write-up are not shown in the UI. They are generated on disk as `deliverables/week10/agent_card.json` and `deliverables/week10/a2a_lifecycle.md`, together with `race_table.md` and `handoffs.log`.

### API checks (optional)

All endpoints require an admin bearer token:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/multiagent/cases` | The 10 selected eval cases |
| GET | `/api/multiagent/results` | Saved race results plus the text deliverables and AgentCard |
| GET | `/api/multiagent/status` | Race job status and progress |
| POST | `/api/multiagent/run` | Start the full race in the background |
| POST | `/api/multiagent/ask` | Run one question through both arms, body `{"question": "...", "inject_failure": false}` |

---

## 9. How each concept from the brief maps to this implementation

| Concept | Where it shows up |
|---|---|
| Orchestrator-worker pattern | `run_multi_agent` in `evaluation/week10_multi_agent.py` |
| Narrow specialists, fewer tools | Triage has no tools, policy worker has one retrieval tool |
| Context re-send cost | `handoffs.log`, hand-off table and share chart in the UI |
| Single vs multi race on the same cases | `evaluation/week10_race.py`, same 10 cases and same judge |
| Four numbers (pass rate, p50 and p99, tokens, cost) | `race_table.md` and the metric cards |
| Multiplier and dominant hand-off | Multiplier line in `race_table.md`, banner and bars in the UI |
| Worker failure behaviour | `inject_failure` in `run_policy_worker`, `failure_case.md` |
| Sunk-cost bias | Named at the top of `verdict.md` |
| Keep or kill with evidence | Rule fixed before the run, applied in `write_verdict` |
| AgentCard | `AGENT_CARD` and `agent_card.json` |
| A2A task lifecycle | `a2a_lifecycle.md` and the lifecycle steps in the UI |
| MCP vs A2A | Pattern card in the UI and the concept README |
| When multi-agent helps | Pattern card and verdict closing line |

---

## 10. Known limits and next steps

- The orchestrator always runs triage first. A router that skips triage for questions that already contain a canonical code would cut tokens.
- The synthesis step could be dropped for answers whose citations already validate. That removes about 30% of multi-agent tokens, but would be a different design than the one measured here.
- The A2A work is a design mapping (AgentCard and lifecycle write-up), not a running A2A server.
- Re-run the race after any prompt change; the saved numbers describe only the recorded run.

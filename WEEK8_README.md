# Week 8 -- Agent Failure Modes & Trajectory Evals

## Problem Statement

The billing support ticket agent passes its outcome eval (correct final answer) but support does not trust it. Twice last week it drafted a correct refund reply after never actually opening the order record. A right answer down a wrong path is a time bomb with a passing test. This week: score the path, expose the gap as a number, and kill the worst failure mode with the price tag attached.

## Concepts Implemented

| Concept | Where It Shows Up |
|---------|-------------------|
| Agent failure modes (loops, wrong tool, hallucinated args, silent failure, skipped tool, extra steps) | `agent/trajectory_eval.py` -- failure mode taxonomy and classifier |
| Trajectory evaluation vs outcome evaluation | Results tab -- per-ticket outcome vs trajectory pass/fail |
| Expected tool sequences (with alternate paths for branching tickets) | `agent/tickets.py` EXPECTED_SEQUENCES; Sequences tab |
| Tool-choice accuracy | Results tab metric card |
| Argument validity rate | Results tab metric card |
| Step efficiency (optimal/actual) | Results tab metric card |
| Cost p50 and max (not mean) | Results tab metric card |
| Outcome-vs-trajectory gap | Gap Analysis tab -- the number and the named example |
| Prompt injection (direct and indirect) | Security tab -- 3 injection payloads |
| Tool sandboxing and least privilege | `agent/mitigations.py` -- argument validation wrapper |
| Output validation | `agent/injection_test.py` -- sanitize_tool_output |
| OWASP LLM Top 10 | LLM01 (Prompt Injection) and LLM08 (Excessive Agency) demonstrated |

## Architecture

```
Frontend (Angular 19)                    Backend (FastAPI)
/trajectory route                        /api/trajectory/* endpoints
  |                                        |
  +-- Expected Sequences tab    <----  GET  /expected-sequences
  +-- Results tab               <----  POST /run + GET /status + GET /results
  +-- Gap Analysis tab          <----  (computed from /results)
  +-- Mitigation tab            <----  POST /mitigate + GET /mitigation-status + GET /mitigation-results
  +-- Regression tab            <----  (computed from /mitigation-results)
  +-- Security tab              <----  POST /injection/run + GET /injection/status + GET /injection/results
                                         |
                                    agent/trajectory_eval.py  -- eval engine
                                    agent/mitigations.py      -- argument validation wrapper
                                    agent/injection_test.py   -- injection test harness
                                    agent/agent_loop.py       -- core agent loop (dispatch_override added)
                                    agent/tickets.py          -- EXPECTED_SEQUENCES, EXPECTED_ARGS added
```

### Key Files

| File | Purpose |
|------|---------|
| `agent/tickets.py` | 10 tickets, expected verdicts, EXPECTED_SEQUENCES (with alternate paths), EXPECTED_ARGS |
| `agent/trajectory_eval.py` | Core eval engine: TrajectoryRecorder, run_single_trajectory, run_full_eval, failure mode classifier |
| `agent/mitigations.py` | Argument validation wrapper (the ONE mitigation), before/after comparison runner |
| `agent/injection_test.py` | 3 injection payloads, sanitizing dispatch, defense system prompt |
| `agent/agent_loop.py` | Added `dispatch_override` parameter for pluggable mitigations |
| `api/trajectory_router.py` | 9 API endpoints for trajectory eval, mitigation, and injection testing |
| `frontend/.../trajectory/` | Angular component with 6 tabs |
| `frontend/.../trajectory.service.ts` | HTTP service for all trajectory endpoints |

## How to Run

### Prerequisites

- Python 3.11+
- Node 18+
- Groq API key (set `GROQ_API_KEY` in `.env`)
- Google OAuth client ID (set `GOOGLE_CLIENT_ID` in `.env`)

### Start Backend

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

### Start Frontend

```bash
cd frontend
npm install
ng serve --port 4200
```

### Access

1. Open `http://localhost:4200`
2. Log in with Google
3. Click "Trajectory" in the nav bar

## Demo Walkthrough (Step by Step)

### Step 1: Expected Sequences (Tab 1)

- Shows all 10 expected tool sequences asserted in code
- T001-T007 and T009-T010 have one valid path: `get_ticket -> get_order -> get_customer_tier`
- T008 shows TWO valid paths (branching: agent may retry with O208-ALT)
- Each ticket shows its expected arguments

**Rubric:** "Trajectory eval over 10 cases with expected tool sequences asserted in code, and legitimate alternate paths accepted rather than over-asserted" (20 pts)

### Step 2: Run Trajectory Eval (Tab 2)

- Click "Run Trajectory Eval" -- takes ~3-5 minutes (Groq rate limits)
- Progress shows which ticket is being evaluated
- When done, four metric cards appear:
  - **Tool-Choice Accuracy** -- fraction of tickets where every tool was correct
  - **Argument Validity Rate** -- fraction of all tool calls with valid args
  - **Step Efficiency** -- mean(optimal/actual) across tickets
  - **Cost** -- p50 AND max (not bare mean)
- Per-ticket table shows pass/fail for each dimension
- Click any row to expand: see actual tool sequence, failure modes, agent reply

**Rubric:** "All four trajectory numbers reported, including cost variance (p50 and max), not a bare mean" (20 pts)

### Step 3: Gap Analysis (Tab 3)

- Large display: `Outcome Pass: X/10 - Trajectory Pass: Y/10 = Gap: Z`
- Shows the gap as a number
- Highlights the right-answer-wrong-path example with:
  - Which ticket it was
  - What the agent did wrong (failure modes)
  - What the actual tool sequence was
  - Why the answer was still correct
- Lists ALL right-answer-wrong-path tickets

**Rubric:** "Outcome-vs-trajectory gap reported as a number plus one named right-answer-wrong-path case with its trajectory shown" (25 pts)

### Step 4: Apply Mitigation (Tab 4)

- Shows the single mitigation: argument validation
- Click "Apply Mitigation & Re-Run" -- runs 20 total agent calls (10 baseline + 10 mitigated)
- Before/After comparison cards with delta arrows:
  - Tool-choice accuracy delta
  - Argument validity rate delta
  - Step efficiency delta
  - Gap delta
- Top failure mode: before count -> after count
- **Price paid** (measured, not asserted):
  - Added latency (mean delta in seconds)
  - Added tokens (mean delta)
  - Added cost per ticket (mean delta in USD)

**Rubric:** "Exactly ONE mitigation, top mode before -> after, with the price paid measured as a number rather than asserted to be free" (25 pts)

### Step 5: Regression Check (Tab 5)

- Per-mode regression table: Mode | Before | After | Delta | Status
- Status: IMPROVED (green), UNCHANGED (neutral), WORSENED (red), NEW (red)
- Summary banner: "No regressions detected" or names the modes that worsened
- Lists all modes checked

**Rubric:** "Regression check across all modes, honestly naming any mode that worsened or appeared" (10 pts)

### Step 6: Security / Injection Testing (Tab 6, Bonus)

- Shows 3 injection payloads planted in deny-case tickets
- Click "Run Injection Tests" -- runs each payload undefended then defended
- Side-by-side results:
  - Undefended: VULNERABLE (red) or SAFE (green)
  - Defended: DEFENDED (green) or BYPASSED (red)
- "What still gets through" -- honest reporting per payload
- Defenses applied: system prompt hardening + output sanitization + argument validation

## Submission Checklist Mapping

| Checklist Item | Where to Demo |
|----------------|---------------|
| 10 expected tool sequences with alternate paths marked | Tab 1: Expected Sequences |
| Results table: tool-choice accuracy, argument validity, step efficiency, cost p50 and max | Tab 2: Results |
| The gap number and one right-answer-wrong-path ticket trace | Tab 3: Gap Analysis |
| Single mitigation diff, before -> after count, measured price | Tab 4: Mitigation |
| Per-mode regression table covering every mode | Tab 5: Regression |

## Key Numbers to Bring to Review

Fill these in after running the eval:

- Tool-choice accuracy: ____%
- Argument validity rate: ____%
- Step efficiency: ____%
- Cost p50: $______, Cost max: $______
- Outcome-vs-trajectory gap: ____
- Top failure mode: ________ (before: ____ -> after: ____)
- Mitigation price: +____ms latency, +____ tokens, +$______ cost/ticket

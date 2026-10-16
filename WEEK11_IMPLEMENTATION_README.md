# Week 11 Implementation: Observability, Cost and the Failure-to-Test Loop

Task Set A (Customer support tickets): "a customer said it gave a wrong answer about refunds yesterday afternoon."
No trace id, no timestamp, no ticket number. Find it from logs, then make sure it cannot ship again.

The concept explanations (what, why, alternatives, negatives) live in `deliverables/week11/README.md`.
This file explains what was built and how to demo it.

---

## 1. What was built, at a glance

| Area | What it does | Where |
|---|---|---|
| Trace storage | Every request is one trace in **Langfuse**, the only trace store. Nothing is written to SQLite or a file. | `src/generation/answer.py`, `src/observability/trace_store.py` |
| Per-request cost | Tokens converted to USD, split by stage (retrieval / generation / tools) | `src/generation/cost.py`, `src/generation/answer.py` |
| Prompt versioning | One `PROMPT_VERSION` constant stamped on every trace | `src/generation/answer.py` |
| Logging | Python `logging` line per request (latency, tokens, cost, citations) | `src/generation/answer.py` |
| Support drill tool | CLI to slice traces by time, keyword, version, cost, unverified answers | `scripts/search_traces.py` |
| Bad trace planter | Plants the refund failure from "yesterday afternoon" | `scripts/plant_bad_trace.py` |
| Eval case + assertion | `G07` regression case and a deterministic `refuses_corpus_gap` check | `evaluation/eval_set.jsonl`, `evaluation/assertions.py`, `evaluation/run_eval.py` |
| Prompt fix | Rule 7 added: no refund/fee/compensation claims unless a chunk states them; version `v1` to `v2` | `src/generation/prompts.py` |
| Cost report | Cost per query by stage from real traces | `scripts/cost_analysis.py` |
| Email alerts | Critical traces trigger an email, sent from a background thread | `src/observability/alerting.py` |
| Single-case check | Run one eval case and print PASS/FAIL (fast RED/GREEN demo) | `scripts/check_case.py` |
| Observability API | Admin-only REST endpoints for traces, cost, 10x, alerts, drills, feedback and eval history | `api/observability_router.py` |
| Answer feedback | Thumbs up or down under each chat answer, stored, scored in Langfuse, thumbs down emails the admin | `api/feedback_router.py`, `src/observability/feedback.py`, chat component |
| Observability page | Angular admin page with four tabs (drill, cost, alerts, failure to test) | `frontend/src/app/components/observability/` |
| Eval runner | Runs one case or the whole suite from the API and stores run history | `src/observability/eval_runner.py` |
| API tests | Tests for auth, filters, eval cases, alerts, drills, stats, 10x, email templates and feedback | `tests/test_observability.py` |
| Deliverables | drill, trace, cost, 10x, suite RED and GREEN outputs | `deliverables/week11/` |

---

## 2. How a request flows now

```
user question
     |
     v
answer_question()                      src/generation/answer.py
     |
     |-- pre-retrieval relevance gate
     |-- retrieval (hybrid BM25 + dense, local)        measured: retrieval_ms, cost 0
     |-- post-retrieval score gate
     |-- LLM generation (Groq)                         measured: generation_ms, tokens, cost
     |-- citation validation
     |
     v
_write_trace()
     |-- calculate_cost()                              src/generation/cost.py
     |-- logger.info(...)                              one structured log line
     |-- update the Langfuse trace with a full snapshot   (question, answer, chunks, timing, tokens, cost, flags)
     |-- remember the summary in memory                   so feedback and the drill see it before Langfuse ingests it
     |-- (optional) append to traces.jsonl                only if TRACE_JSONL_MIRROR=true, for the old Week 6 pages
     |-- check_and_alert()                             src/observability/alerting.py
              |-- conditions evaluated inline (no I/O)
              |-- if tripped: daemon thread sends SMTP email (request never waits)
```

---

## 3. Implementation details

### 3.1 Where data lives: Langfuse for traces, SQLite for everything else
Traces are **not** stored in your database. Each answered request becomes one Langfuse trace whose metadata holds a full
snapshot (prompt version, model, retrieved chunks and scores, citations, timings, tokens, cost, an `unverified` flag). The
Observability page reads traces back from Langfuse through `src/observability/trace_store.py`.

What stays in SQLite (`data/app.db`), because it is not trace data: user feedback (plus a small snapshot of the question and
answer rated), alert history, drill times, and eval suite history. The old `traces` table in an existing database is left
untouched and unused; nothing reads or writes it. Drop it yourself with `DROP TABLE traces` when you are happy.

How reading works, and the limits that come with it:
- **Langfuse filters by** time window, user (exact email), tag (`prompt:<version>`) and trace name. These are sent to Langfuse.
- **Applied after fetching** (Langfuse cannot do them): keyword in the question or answer, cost above, unverified answers,
  errors, and partial-email user matches. These look at the newest `LANGFUSE_SCAN_LIMIT` traces (default 200) in the
  selected time window. If more exist, the page says so; narrow the time window to reach older traces.
- **Rate limits are the main constraint.** On the plan tested, Langfuse allows **5 trace-list calls and 5 single-trace calls
  per minute**. The code is built around that: one call fills a page, results are cached for `LANGFUSE_CACHE_SECONDS`
  (default 60), one newest-first scan is shared by keyword search, cost statistics and the 10x view, the trace drawer
  uses data already fetched, and a local budget (`LANGFUSE_API_MAX_PER_MIN`, default 5) shows "try again in N seconds"
  instead of failing in Langfuse. Raise these settings if you self-host Langfuse or move to a higher plan.
- **Freshness:** Langfuse takes a few seconds to ingest a trace. Traces made by this API process (and the demo plant) appear
  immediately from memory. Traces made by another process appear within about a minute.
- **Retention:** how long traces are kept depends on your Langfuse plan.
- **Older traces** (made before this change) have no chunk list or full timing, so their drawer says "not recorded". Their cost
  is calculated from their stored token counts.
- If Langfuse is not configured, the Observability page shows a clear message and no traces.

### 3.2 Cost (`src/generation/cost.py`)
- `calculate_cost(model, input_tokens, output_tokens)` uses a per-model price table (USD per 1M tokens) with a default.
- Retrieval is local (ChromaDB, BM25, local embeddings), so its cost is 0. All API cost is generation. Tools cost is 0
  because this pipeline calls none.
- The prices are list prices entered by hand. Verify them against the provider page before quoting absolute numbers.

### 3.3 Prompt versioning and the fix
- `PROMPT_VERSION` in `src/generation/answer.py` is written to every trace, so "which prompt produced this answer?"
  is a query, not a guess.
- `v2` adds rule 7 to the system prompt: never state refund eligibility, windows, fees or compensation unless a
  supplied chunk says so, and related-sounding text (rollbacks, retries) is not a refund policy.
- Canary: serve `v2` to about 10% of traffic for 1 hour and compare non-refusal answers with `citations_valid = 0`
  against the `v1` baseline. Rollback: set `PROMPT_VERSION = "v1"`, restore the old rules, redeploy. Both versions
  stay queryable.

### 3.4 Failure-to-test loop
- `G07` in `evaluation/eval_set.jsonl` is the refund question, linked to the planted trace id.
- `assert_refuses_corpus_gap` in `evaluation/assertions.py`: if a case expects a refusal, the answer must start with
  one of the two refusal wordings used in this codebase. This is deterministic, so it does not depend on the LLM judge.
- `run_eval.py` passes `expected_behavior` into the assertions and prints a fifth column (`refusal`).
- Results (assertion pass counts over 26 cases): **RED 18/26** with the regression reintroduced, **GREEN 23/26** with
  `v2`. Five cases flipped to pass (G01, G02, G05, G06, G07), none flipped to fail. G03, G04 and A05 fail in both
  runs because their `refusal` labels are stale (the corpus now contains those answers). They were not relabelled.
- Raw outputs: `deliverables/week11/suite_red.txt` and `suite_green.txt`.

### 3.5 Email alerts (`src/observability/alerting.py`)
- How the mail is sent: after the trace is saved, `check_and_alert()` evaluates the conditions in memory (instant, no
  I/O). If any trip, it starts a `threading.Thread(daemon=True)` that opens an SMTP connection (STARTTLS), logs in and
  sends. The user's request has already returned by then. There is no queue, Celery or Redis.
- Conditions: non-refusal answer without valid citations; cost above `ALERT_COST_THRESHOLD`; latency above
  `ALERT_LATENCY_THRESHOLD_MS`; any pipeline error; answer containing "refund", "compensation" or "guarantee"
  without being a refusal.
- Rate limit: at most one email per alert type per 5 minutes, tracked in a lock-protected dict inside the process.
  It resets on restart and is per process, not shared across several workers.
- Failures are logged and swallowed, so a broken SMTP server can never break an answer.
- Free option used: Gmail SMTP with an App Password (about 500 emails/day). Mailtrap's free sandbox works for testing
  by changing the host and port.
- Off by default (`ALERT_EMAIL_ENABLED=false`). Settings are listed in `.env.example`.
- Limitation: a daemon thread can be killed mid-send if the process exits, so a very recent alert can be lost.

### 3.6 Observability page (Angular) and API

It is the **Observability** tab in the Admin hub (`/admin`), next to Traces and Eval, so it is visible to admins only (same `adminGuard`).
All API routes live under `/api/obs` and require an admin JWT (401 without a token, 403 for a normal user).

| Tab | What you can do | API |
|---|---|---|
| Traces and support drill | Filter by UTC time window, keyword, prompt version, cost, unverified answers, errors. Start a stopwatch, open a trace, press "This is the bad answer" to record time-to-find and the slice you used. The trace drawer shows per-span latency, tokens and cost, retrieved context ids, and can turn the trace into an eval case. | `GET /traces`, `GET /traces/{id}`, `POST /traces/{id}/eval-case`, `POST /drills`, `GET /drills` |
| Cost and 10x | Cost per request with p50 and p95, cost by stage, a before and after table by prompt version (with the model shown, so a model change is not mistaken for a saving), and a 10x calculator that names the constraint that breaks first. | `GET /stats`, `GET /tenx` |
| Email alerts | Masked configuration, the conditions that fire an alert, a "Send test email" button, and alert history (sent, failed, suppressed, test). | `GET /alerts/config`, `GET /alerts`, `POST /alerts/test` |
| Failure to test | Suite run history with pass counts, run one case or the full suite (background thread, one at a time), compare two runs to see fixed, regressed and still failing cases, and read per-case assertion details. | `GET/POST /eval/...` |

Design choices worth knowing:
- Time inputs are UTC, and the page says so. Stored timestamps are UTC, so "yesterday afternoon" does not shift with the browser time zone.
- Keyword search escapes `%` and `_`, so a user cannot turn the search into a wildcard scan.
- Secrets never reach the browser: emails are masked and the app password is only reported as set or not set.
- "Send test email" is rate limited to once per 20 seconds. Eval suite runs and single-case runs cannot overlap, and a run left `running` by a crashed process is marked as an error after 30 minutes.
- Eval runs here use the deterministic assertions only (no LLM judge), so pass counts are reproducible and cheap.
- New tables: `alerts`, `drills`, `eval_suite_runs`, `eval_run_results`, created by `init_db()`.
- Settings (all in `.env.example`): `OBS_DEMO_TOOLS` (default false, shows the "Plant a bad answer" button), `OBS_LIMIT_TPM`, `OBS_LIMIT_RPD`, `OBS_LIMIT_RPM` (the provider limits the 10x calculator uses).

### 3.7 Tracing with Langfuse (open source)

Langfuse is the tracing UI. It is open source, you can self-host it, and it was already wired into the pipeline
(`src/generation/langfuse_client.py`). This week it was made to match the rest of the system:

- **One trace, one id.** `answer_question()` creates the trace id up front and uses it for the Langfuse trace, the feedback
  rows and the eval results. The **Open in Langfuse** button in the trace drawer links straight to it
  (`<LANGFUSE_HOST>/trace/<trace id>`).
- **Who and which prompt.** The Langfuse trace carries the user's email as `user_id`, the prompt version as `version` and a
  `prompt:<version>` tag, so you can filter by user or compare prompt versions in Langfuse.
- **Cost per generation.** Input, output and total cost are sent with the token counts.
- **Feedback as scores.** See 3.8.

Langfuse stays optional: with no keys in `.env` nothing is sent and the page shows a "langfuse off" chip. Only requests made
after this change have matching ids, so older traces have no working Langfuse link.

### 3.8 User feedback: thumbs up and down

Under every answer in **Chat** (RAG mode) there is a thumbs up and a thumbs down.

- **Thumbs up** is saved immediately.
- **Thumbs down** opens a short form: choose a reason (wrong answer, did not answer my question, missing information,
  outdated, hard to understand, something else) and optionally explain what the answer should have said.
- One vote per user per answer. Changing your mind updates the same vote.

What happens on a thumbs down (`src/observability/feedback.py`):
1. The vote, reason and comment are stored in the `feedback` table, linked to the trace id.
2. Two scores are added to the Langfuse trace: `user-feedback` (true or false, with the comment) and `user-feedback-reason`
   (the reason). Voting again updates the same scores instead of adding new ones.
3. The admin gets an HTML email with the user, the reason and comment, the question, the answer, and two buttons: **Review the
   trace** (opens Admin, Observability, that trace) and **Open in Langfuse**. It goes to `ALERT_EMAIL_TO`.
4. Steps 2 and 3 run on a background thread, so the user never waits for Langfuse or SMTP.

Email rules: sent only for a new thumbs down (not for repeats or a thumbs up), capped at `FEEDBACK_EMAIL_MAX_PER_HOUR` (default 20) so a
burst cannot flood the admin, and every outcome (sent, failed, suppressed) is recorded in alert history. If email alerts are
off or not configured, the vote is still saved and shown in the admin inbox.

Admin side (Admin, Observability, **User feedback** tab): a red badge shows new thumbs down. The list shows who voted, when, why
they disagreed, the question and answer, and the prompt version. For each vote you can **Open trace** (full spans, retrieved
context and the user's comment), open it in Langfuse, **add it as an eval case** from the trace drawer, and **Mark reviewed**
with a note. The trace table also has a **User email** filter, and the trace drawer shows who asked and any feedback on it.

That is the optimization loop: thumbs down, email, open the trace, see what was retrieved and answered and why the user
disagreed, add an eval case, fix the prompt or retrieval, and compare runs in Failure to test.

Safety: feedback needs a signed-in user, is limited to 30 votes per user per 10 minutes, comments are capped at 1,000 characters,
and every value is HTML-escaped in the email.

Limits: feedback is only offered on RAG answers. Agent mode answers have no trace to attach it to.

---

## 4. Demo in the Angular UI

### Start the app
Stop any API already running on port 8000 first: it will not have the new routes until it is restarted.

```powershell
.\.venv\Scripts\Activate.ps1
$env:OBS_DEMO_TOOLS = "true"
python -m uvicorn api.main:app --port 8000
```

In a second terminal:

```powershell
cd frontend
npx ng serve --proxy-config proxy.conf.json
```

Open http://localhost:4200 and sign in with the admin Google account (the one in `ADMIN_EMAIL`). The first request after a
restart is slow (about 20 seconds) because the embedding model loads. Click **Admin** in the top bar, then the **Observability** tab.

### Part A: support drill (about 3 minutes)
1. On **Traces and support drill**, click **Plant a bad answer (demo)**. A fabricated refund answer from yesterday afternoon is added.
2. Click **Start drill**. The stopwatch starts and the complaint is shown: "a customer said it gave a wrong answer about refunds yesterday afternoon."
3. Click **Yesterday 12:00 to 18:00 UTC**, type `refund` in Keyword, click **Search**. One trace matches, marked "unverified".
4. Click the row. The drawer shows the answer, the spans table (latency, tokens, cost), the retrieved context ids, and which spans are "not logged".
5. Click **This is the bad answer**. The banner shows your time in mm:ss, whether it beat the 5:00 bar, and the slice you used. It is saved under "Previous drills".
6. Optional: try the other slices. Tick **Unverified answers** with no keyword and the same trace appears.

### Part B: close the loop (about 2 minutes)
1. In the trace drawer, under **Close the loop**, keep "refuse" selected and click **Add as eval case**. A case such as `PF01` is appended to `evaluation/eval_set.jsonl`. Click **Open Failure to test**.
2. In **Eval cases**, find the new case and click **Run**. It runs against the live pipeline and shows RED or GREEN with the failing check.
3. In **Suite runs**, you see the earlier `v1-regressed` run (18/26) and the `v2` run (23/26). Click **Compare**: 5 fixed, 0 regressed, 3 still failing. "0 regressed" is what proves the fix did not break anything else.
4. Optional: click **Run full suite** for a live run. It runs in the background (a few minutes) and the table updates by itself.

The suite history lives in SQLite. A fresh database starts with no runs: click **Run full suite** to create the first one.

### Part C: cost and 10x (about 2 minutes)
1. Open **Cost and 10x**. Read the cost per request, per 1,000 requests, and the stage table (retrieval costs nothing, generation is all of the cost).
2. In **Before and after, by prompt version**, compare rows. Check the Model(s) column first: rows that use different models are not a fair prompt comparison.
3. In **What breaks first at 10x?**, set baseline requests per minute (for example 5) and multiplier 10. The verdict names the limit that breaks first and the table shows the ratio for each limit.

### Part D: email alerts (about 2 minutes)
Alert emails are HTML (with a plain-text fallback): a colored header per alert type, a plain-language explanation, why it fired
and what to do, a details table (time, trace id, prompt version, model, cost, latency), the question and answer, and an
**Open this trace** button. The button opens `ALERT_APP_URL/admin?tab=observability&trace=ID`, which opens the Observability tab in Admin and jumps straight to that trace
(you must be signed in as an admin). All question and answer text is HTML-escaped before it goes into the email.

1. Open **Email alerts**. It shows whether alerts are enabled, the masked addresses, the thresholds and the conditions.
2. If something is missing, the page lists exactly which settings to add to `.env`, and the test button stays disabled.
3. Click **Send test email**. It sends one real email to the configured address. A new row appears in Alert history with status `test`, or `failed` with the reason.
4. Alerts raised by real traffic show here too, for example an `ungrounded_answer` row when an answer has no valid citations.

### Part E: thumbs down, email and Langfuse (about 4 minutes)
1. Sign in as a normal user (or as the admin) and open **Chat**. Ask "Can I get a refund if my billing migration fails?".
2. Under the answer click the thumbs down, choose a reason, write why, and click **Send feedback**. You see "Thanks, we will look into it."
3. The admin mailbox (`ALERT_EMAIL_TO`) gets an email titled "Thumbs down" with the reason, your comment, the question, the
   answer and a **Review the trace** button. This needs email alerts enabled (see Part D).
4. As admin open **Admin, Observability, User feedback**. The tab shows a red badge, and the row shows who voted, why, the question
   and the answer. Click **Open trace** to see the spans, the retrieved context and the feedback on that trace.
5. Click **Langfuse** (or **Open in Langfuse** in the drawer). The trace there has the user, the prompt version, the cost and two scores,
   `user-feedback` and `user-feedback-reason`. Langfuse asks you to sign in to your project.
6. Close the loop: in the drawer click **Add as eval case**, fix the prompt, run the case in **Failure to test**, then click
   **Mark reviewed** on the feedback row and leave a note.

### After the demo
The planted demo trace, the drill record and any `PF` eval case are real rows and lines in your data. Delete the `PF` lines from
`evaluation/eval_set.jsonl` if you do not want them kept. Turn `OBS_DEMO_TOOLS` off (or unset it) for normal use.

---

## 5. Step by step demo with scripts (optional)

Run everything from the project root in PowerShell. First activate the project's virtual environment (once per
terminal). The system `py` does not have the project's packages and fails with
`ModuleNotFoundError: No module named 'requests'` or `'dotenv'`.

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONIOENCODING = "utf-8"
```

The prompt must now start with `(.venv)`. The second line avoids encoding errors, because model answers contain
non-ASCII characters. If activation is blocked by an execution policy error, run
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and activate again. Always use `python`, never `py`.

Prerequisite: `.env` contains `LLM_PROVIDER=groq` and a valid `GROQ_API_KEY`.

### Step 1: check that Langfuse is reachable
```powershell
python scripts/search_traces.py --limit 3
```
Expect the 3 newest traces from Langfuse. If you see "Langfuse is not configured", add `LANGFUSE_PUBLIC_KEY` and
`LANGFUSE_SECRET_KEY` to `.env`. Remember the plan allows only 5 list calls per minute: wait a minute between heavy commands.

### Step 2: plant the bad answer (the incident)
```powershell
python scripts/plant_bad_trace.py
```
Creates a fabricated "full refund within 30 days" trace in Langfuse, tagged `demo-planted`, timestamped 2026-10-11 14:32 UTC. Re-running updates the same trace. It takes a few seconds to show in Langfuse.

### Step 3: the support drill (find it from the vague complaint only)
Start a stopwatch, read the complaint, then run:
```powershell
python scripts/search_traces.py --after "2026-10-11 12:00" --before "2026-10-11 18:00" --keyword refund
```
Expect exactly one trace: the fabricated refund answer, `valid=0`. Stop the stopwatch and write the time in
`deliverables/week11/drill.md`. Other slices to show:
```powershell
python scripts/search_traces.py --bad-citations --after 2026-10-11 --before 2026-10-12
python scripts/search_traces.py --prompt-version v1 --cost-above 0.0001
```

### Step 4: inspect the found trace (per-span latency, tokens, cost, context ids)
```powershell
python scripts/search_traces.py --trace-id 8ebfc75d-5499-4c3f-b606-2bb07a201a7c --json
```
The pasted, per-span version is `deliverables/week11/trace.json` (prompt version, retrieved context ids, spans).

### Step 5: generate a real traced request and see its cost
```powershell
python -c "from src.generation.answer import answer_question; a = answer_question('What does ERR-4032 mean?'); print(a.final_answer[:160])"
python scripts/search_traces.py --limit 1
```
The newest row shows the timestamp, `pv=v2`, and `cost=$...`. This proves new requests are logged with cost and version.

### Step 6: cost per query by stage
```powershell
python scripts/cost_analysis.py --prompt-version v2
```
Shows the stage table (retrieval 0, generation about $0.00028, tools 0), median, p95, and cost per 1,000 queries.
Written up in `deliverables/week11/cost_by_stage.md`; the 10x answer is in `deliverables/week11/tenx.md`.

### Step 7: close the loop, GREEN (fast, one case)
```powershell
python scripts/check_case.py G07
```
Expect `prompt_version=v2` and `RESULT: PASS` (the answer is the standard refusal).

### Step 8: show RED, then GREEN, for the refund case
1. In `src/generation/prompts.py` replace rules 5 to 7 with the regression and set `PROMPT_VERSION = "v1-regressed"`
   in `src/generation/answer.py`:
   ```
   5. If the context only partly answers the question, answer as helpfully as you can from the nearest related information.
   6. Be concise and friendly."""
   ```
2. Run `python scripts/check_case.py G07`. Expect `RESULT: FAIL` on `refuses_corpus_gap` (the model no longer gives the
   canonical refusal; in the recorded run it said the docs "don't address refunds").
3. Restore the three rules (5 refusal, 6 no best guess, 7 no financial claims) and set `PROMPT_VERSION = "v2"`.
   Re-run `check_case.py G07` and expect `PASS`.

Use `git diff src/generation/prompts.py src/generation/answer.py` to confirm the files are back to v2 afterwards.

### Step 9: full suite with pass counts (about 5 minutes per run)
```powershell
python evaluation/run_eval.py --judge-version v2 | Tee-Object deliverables/week11/suite_rerun.txt
```
Look at the `ASSERTION RESULTS` table. The TOTAL row ends with the pass count (23/26 on `v2`). The paced Groq calls are
the reason for the duration. Saved reference runs: `suite_red.txt` (18/26) and `suite_green.txt` (23/26).
Note this rewrites `evaluation/answers_25.jsonl` and `evaluation/prediction_v2.json`.

### Step 10: email alerts
Dry run, sends nothing:
```powershell
python scripts/test_alerting.py --dry-run
```
Expect `conditions tripped: ['ungrounded_answer', 'blocklist_keyword']`.

Real email (Gmail): turn on 2-step verification, create an App Password, then set these in `.env` (never commit them):
```
ALERT_EMAIL_ENABLED=true
ALERT_EMAIL_FROM=you@gmail.com
ALERT_EMAIL_TO=you@gmail.com
ALERT_EMAIL_PASSWORD=<16-character app password>
```
```powershell
python scripts/test_alerting.py
```
Expect `email sent` and a message with subject `[RAG Alert] test - trace test-trace`.

Live trigger from a real request (any request now counts as a cost outlier):
```powershell
$env:ALERT_COST_THRESHOLD = "0.00001"
python -c "from src.generation.answer import answer_question; answer_question('What does ERR-4032 mean?'); import time; time.sleep(8)"
```
The `sleep` keeps the process alive long enough for the background thread to send. An email arrives with subject
`[RAG Alert] cost_outlier - trace <id>`. Close the terminal afterwards to drop the temporary threshold.

---

## 6. Honest status and known gaps

- The Observability page was verified in a browser with a locally minted test admin token (Google sign-in was not exercised),
  on desktop and phone widths. "Send test email" was deliberately not clicked, so real SMTP delivery is untested from the page;
  the failure path and history recording are covered by tests with the SMTP call mocked.
- A suite run from the UI was not executed end to end (single-case runs were). The suite worker is covered by a test.
- The page polls every 3 seconds only while a suite run is in progress.

- Human time-to-find (mm:ss) is not recorded. The trace was planted by a script, so a squadmate must time a drill and
  fill it into `deliverables/week11/drill.md`. The bonus (second planted answer, beat your time) is not done.
- No cost improvement has been implemented, so there is no before/after cost number yet. Baseline is about
  $0.00028 per query, all generation. Candidates: prompt caching, semantic cache, routing easy questions to a
  smaller model.
- The real RED reproduction did not invent a refund; it refused in non-standard wording. The assertion catches the
  wording, and the alert rules plus `--bad-citations` catch fabrication.
- G03, G04 and A05 fail in both runs due to stale `refusal` labels in the eval set. Relabelling is the eval owner's call.
- Missing log fields: session_id, ticket_id, and separate latency for the gate and citation-check steps. The user's email is now
  recorded on new traces (older traces have none).
- Feedback and Langfuse were verified in a browser with test users and a test API that had email turned off, so the thumbs-down email
  was never sent through real SMTP; it is covered by tests with the SMTP call mocked. Press a thumbs down yourself to confirm delivery.
- The Langfuse link format matches the SDK's own, but opening it needs a Langfuse sign-in, which was not exercised.
- Feedback is offered on RAG answers only (agent answers have no trace). Traces from before this change have no matching Langfuse id.
- My test requests left a trace and feedback scores for test users in the Langfuse project (users ending in `e2e`); delete them there if you want.
- The old Week 6 pages (Admin, Traces, Sample, Replay) and `scripts/replay_trace.py` read `evaluation/traces.jsonl`, which is no
  longer written. They still work on the traces already in that file. Set `TRACE_JSONL_MIRROR=true` to keep feeding them.
- Langfuse limits (measured): 5 trace-list calls per minute and 5 single-trace calls per minute on the plan tested. Heavy use of the
  page can show "try again in N seconds". Self-hosting Langfuse or a higher plan removes this.
- Keyword, cost and unverified filters only cover the newest 200 traces in the chosen time window (Langfuse cannot filter them).
- Planting a demo trace and the demo drill create a real trace in your Langfuse project (tag `demo-planted`, user
  `demo-customer@example.com`).
- Alert rate limiting is per process and in memory; email send is best effort.
- Prices in `src/generation/cost.py` are unverified list prices.
- The 10x analysis assumes 5 requests/min today (no production traffic exists) and uses this key's limits
  (8,000 tokens/min, 1,000 requests/day).
- `tests/test_structure_chunker.py` has 3 failing tests (`StopIteration`) whose paths point at a different folder;
  they were not investigated against a clean checkout.

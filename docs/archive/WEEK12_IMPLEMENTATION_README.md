# Week 12 Implementation: Tier-1 Deflection Assistant

What was built, what was changed in existing code, how it fits together, what the evidence says, and what is not done.
All data in this project is SYNTHETIC. Companion documents: `WEEK12_CONCEPTS_README.md` (the ideas, explained),
`WEEK12_IMPLEMENTATION_PLAN.md` (the plan this followed), `deliverables/week12/` (the evidence and submission files).

## 1. At a glance

The client's Tier-1 support team answers about 2,000 tickets a month, and two recent escalations came from quoting the
retired 14-day refund window to a 30-day customer. This system answers a Tier-1 ticket from the help centre with a citation
that names the refund-policy version, checks the customer's real entitlement through a tool before saying anything about
refunds or shipping, and escalates to a person instead of guessing.

| Brief requirement | Status | Where |
|---|---|---|
| 1. RAG with version-named citations | Done | `src/retrieval/`, `src/generation/citations.py`, `tier1/customer_text.py` |
| 2. Hand-built agent loop, 3+ tools, MCP tools discovered at runtime | Done | `agent/agent_loop.py`, `agent/mcp_client.py`, `tier1/tools.py` |
| 3. Own MCP server called by a client that is not yours | Server (stdio and HTTP with a bearer token) and guide for three clients done; the outside-reviewer run has not happened | `mcp_servers/help_centre_server.py`, `docs/MCP_CLIENT_GUIDE.md` |
| 4. Eval suite, one command, judge at 85% or more | Suite done (`fix1`: 36 of 39); the Week 6 rubric is re-checked on integrated outputs with a second judge; agreement NOT measured until a person labels 20 replies on `/label` | `evaluation/integrated/` |
| 5. Error taxonomy, 4 to 7 modes, one created by integration | Done (6 modes) | `deliverables/week12/taxonomy.md` |
| 6. Trajectory eval, 10+ cases, outcome-vs-trajectory gap | Done (27 cases combined; 30 cases for the model's own choices, which the prefetch makes the honest measure) | the "Trajectory" section of each eval report |
| 7. One trace id across agent and MCP hops, cost and latency per span, PII held | Done and tested | `src/observability/`, `tier1/tracing_store.py` |
| 8. Closed failure-to-test loop, cost per deflected ticket, 10x plan | Report, case, run (red or green) all in the UI; production-model re-run: wrong source 6 to 3 of 25 on the same cases, held-out A/B inconclusive; $0.000915 per deflected ticket; daily token cap breaks first (about 60 a day). The live demo is still to give | `tier1/eval_cases.py`, `deliverables/week12/closed_loop.md`, `cost_and_10x.md` |
| Angular UI (added to the plan) | Done | `frontend/src/app/components/tier1/` |

## 2. How one ticket flows

Entry points (the Angular UI through the API, the CLI, and the eval suite) all call one function, `handle_ticket()` in
`tier1/service.py`, so the evals grade exactly what a user sees.

1. **Trace opened.** A trace id is created and a root span starts.
2. **Pre-guard** (`tier1/guards.py`, no model call): legal threats, chargebacks, safety, fraud or account-security language,
   prompt-injection patterns and oversized tickets escalate immediately, at zero model cost.
3. **Agent loop** (`agent/agent_loop.py`): the model works within budgets (6 laps, 14,000 tokens, 120 seconds; the help-centre
   search is capped at 2 calls, enforced in code). It can call `check_entitlement`, `lookup_order`, `search_help_centre` and
   `escalate`, all over MCP, discovered when the manager connects and filtered by an allow-list.
4. **Post-guard** (`tier1/guards.py`, no model call): the draft is blocked unless entitlement was checked, every citation resolves
   to a chunk that was actually retrieved, the cited refund-policy version matches the customer's, the stated window is right,
   and the reply does not claim a refund was issued.
5. **Decision.** `ANSWER` only if every check passes; anything else is `ESCALATE` with a handoff row and the blocked draft kept
   for a person. A tool failure, a provider failure and a budget hit all end in `ESCALATE`, never in a guess.

Principle throughout: code decides anything about money, eligibility, policy version or escalation; the model writes prose
and chooses which tool to call. No tool can move money; `escalate` is the only write tool and it only queues a handoff.

## 3. What was built (new)

### 3.1 Data: a synthetic Variant A corpus
No real corpus was available, so `scripts/generate_synthetic_corpus.py` (seed 1201, frozen as-of date 2026-10-01)
generates: 120 help articles (30 topics x 4 variants), 40 Zendesk macros, the refund policy in BOTH forms (retired 14-day,
current 30-day), a shipping SLA matrix for 6 regions, a changelog, 60 customers (19 on the legacy 14-day policy), 300 orders
and 300 resolved tickets. Three of the macros quote the retired 14-day window on purpose: that is where the original
failure came from. Every record is tagged `synthetic: true`. Output is in `data/variant_a/synthetic/`.
`scripts/ingest_variant_a.py` builds the vector index (164 documents, 951 chunks) with the existing chunker, unchanged.

### 3.2 `tier1/`: the core package
| File | Purpose |
|---|---|
| `service.py` | `handle_ticket()`, the single entry point, with an optional progress callback for the UI |
| `guards.py` | Pre-guard and post-guard (section 2). Normalises Unicode before matching, because the model emits lookalike characters |
| `prompts.py` | System prompt (built from the discovered tool schemas) and the ticket framing; ticket text is marked as untrusted data |
| `tools.py` | `lookup_order`, `check_entitlement` (refund eligibility computed here from order age and the customer's window), `escalate` |
| `db.py`, `store.py` | The SQLite store (`data/tier1.db`) and every query behind the API (queue, results, decisions, feedback, escalations, jobs, metrics) |
| `tracing_store.py` | Writes spans, rebuilds the trace tree, totals cost and time |
| `customer_text.py` | Turns the model's draft (which cites raw chunk ids) into customer-ready text: numbered `[1]` markers, a Sources footer, the customer's first name in the greeting |
| `eval_cases.py` | Turns a reported failure into a permanent regression case |
| `models.py`, `masking.py`, `flags.py`, `__main__.py` | Request/response shapes; email and name masking for lists; test switches for before/after runs; the `python -m tier1` CLI |

### 3.3 MCP servers
- `mcp_servers/tier1_tools_server.py`: `lookup_order`, `check_entitlement`, `escalate`.
- `mcp_servers/help_centre_server.py`: `search_help_centre(query, policy_version, top_k, include_macros)`. This is the capability exposed
  to outside clients. It warms its embedding model before serving (a cold first call took over 100 seconds) and, by default, never
  returns internal macros.
- `mcp_config.tier1.json`: which servers to start and which tools each may expose (the allow-list).
- Both servers take hidden `trace_id` and `parent_span_id` arguments, injected by the client and removed from the schema the model sees.

### 3.4 LLM gateway: `src/generation/gateway.py`
The one door to the model provider. Disk cache keyed by the full request; a sliding-window tokens-per-minute limiter so requests
wait before being refused; retries with backoff for 429 and 5xx; a distinct `RateLimited` error that fails immediately for a
daily or long cap; cache modes `readwrite`, `off` (production), `replay` (CI, no network).

### 3.5 Observability and privacy
- `src/observability/tracing.py`: spans with start, duration, tokens, cost and status; free text is never stored.
- `src/observability/redact.py`: PII redaction applied at every sink, in three layers: field names, patterns (email, address,
  phone, Luhn-checked card, SSN-like) and exact values from the customer table. Customer and order ids become salted hashes.
  Wrapped around the one Langfuse client, the span writer, alert emails, handoff summaries and the saved MCP wire log.
- `scripts/export_trace.py`: prints a trace as a waterfall and writes JSON; `deliverables/week12/trace.json` is one real trace.

### 3.6 API: `api/tier1_router.py`
Thin; every decision comes from `handle_ticket`. 17 routes under `/api/tier1`:

| Route | Purpose |
|---|---|
| `GET /tickets`, `GET /tickets/{id}` | Queue (customer masked, no eval ground truth) and ticket detail (real email only here) |
| `POST /answer`, `GET /jobs/{id}` | Start a run as a job and poll its live steps; at most 2 run at once, then a 429 |
| `POST /tickets/{id}/decision` | approve, edit, escalate, reject; records an edit ratio against the customer text |
| `POST /feedback`, `GET /feedback`, `POST /feedback/{id}/eval-case` | Report a wrong answer; the admin inbox; turn a report into a regression case |
| `GET /escalations`, `POST /escalations/{id}/status` | Handoff queue; claim and resolve |
| `GET /articles/{slug}` | Article text for the source drawer, flagged `retired` for the 14-day policy |
| `GET /customers`, `GET /random-ticket` | Try-a-ticket picker; a reproducible random draw (seed returned) |
| `GET /metrics`, `GET /traces/{id}`, `POST /eval/run`, `GET /eval/runs/{id}` | Admin only: insights, trace spans, run the eval suite |

### 3.7 Who sees what

A regular signed-in user sees ONE page, the chat, in two modes. **Docs** searches the help centre. **Agent** runs the Tier-1
assistant as their own customer account (matched on the sign-in email; the admin alone gets an act-as picker; `TIER1_DEMO_CUSTOMER_ID` is a demo-only fallback): live steps, a cited answer, Copy reply, Report wrong answer, and a plain "passed to our
team" message when it escalates. The user never sees the blocked draft, guard findings or handoff detail (the API strips them from
the job result), and can only read their own jobs. Everything else is admin only, in the API (403) and the UI (route guards, no
nav links): ticket queue and review, random ticket, approve/edit/escalate decisions, escalations (list, claim, resolve), Try a
ticket, Insights, traces, review inbox and eval runs. Escalation is an admin operation.

### 3.8 Angular workspace: `frontend/src/app/`
Admin screens under `components/tier1/` (users only get the chat page, section 3.7): ticket queue (filters kept in the URL, keyboard `j k Enter / ?`), ticket workspace (ticket,
customer and order; entitlement card; editable draft with source chips; live "how I got here"; approve, edit, run again, escalate,
report wrong answer; `Ctrl+Enter`, `E`, `R`, `Shift+E`), Try a ticket (random draw or your own), Escalations, Insights (lead only:
quality, deflection next to re-open, failures, review inbox, run the suite) and a trace waterfall. Shared pieces in `shared/`:
status chip, policy badge, KPI tile, decision banner, entitlement card (loud when entitlement was not checked), step timeline,
source drawer (highlights the cited passage, warns on retired policy), accessible modal, toasts. A light theme was added beside the
existing dark one; both were checked. One typed API client, `services/tier1.service.ts`.

### 3.8 Evaluation suite: `evaluation/integrated/`
`python -m tier1 eval` runs 39 cases through `handle_ticket`: 20 drawn at random (seed 1212) from all 300 tickets, plus the slices
the brief requires (3 refund questions each asked by a legacy and a current customer, delivery by region, must-escalate, not Tier-1,
two injections, missing order). Order of evaluation: exact assertions first, then a judge (`qwen/qwen3.8-27b`, a different model
family from the `gpt-oss` agent) on answered replies only. Outputs: per-slice and per-check pass rates, the both-versions slice
reported separately, the superseded-policy rate, trajectory accuracy and gap, cost per deflected ticket, a failure-mode tally with
trace ids, a blind label sheet for a human, and an explicit "what this does NOT cover" list. `second_contact.py` is the bonus
(deflection and simulated re-open together, with a human-reply control). `cases_holdout.jsonl` holds 15 tickets the fixes were
not derived from. `--ablate` switches defences off to measure before and after.

### 3.9 Packaging and docs
`Makefile` and `tasks.ps1` (one command per job), `Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`,
`.github/workflows/ci.yml`, `docs/MCP_CLIENT_GUIDE.md`, a Tier-1 section in the root `README.md`, diagrams in
`deliverables/week12/diagrams/` (architecture SVG and Mermaid, and a database entity diagram checked against the real schema).

## 4. What was enhanced in existing code

| File | Change |
|---|---|
| `agent/agent_loop.py` | Calls the model through the gateway; one MCP manager per config; liveness check and a 60-second fast-fail after a failed connect; per-tool call caps enforced in code; a span for every model call and tool call; the trace id and a parent span id passed to tools; a rate limit becomes a labelled error |
| `agent/mcp_client.py` | Per-server tool allow-list; hidden `trace_id` and `parent_span_id` arguments; tools read from either spelling of the SDK's schema attribute; configurable connect and tool timeouts; forwards the environment variables a server needs; `is_alive()` and `close()`; the saved wire log is redacted |
| `src/retrieval/search.py`, `bm25_search.py`, `hybrid_search.py`, `filters.py` | Metadata filters now reach BOTH retrievers (before, `hybrid_search` ignored them); results carry slug, document type, policy version and date; `policy_where()` and `customer_where()` (excludes internal macros) |
| `src/generation/citations.py` | `resolve_citations()` and `check_policy_citations()`; strips invisible characters; tolerates spaces inside the brackets |
| `src/generation/langfuse_client.py` | The single Langfuse client is wrapped so every trace is redacted |
| `src/observability/alerting.py` | Alert emails are redacted |
| `api/main.py` | Mounts the Tier-1 router |
| `src/config.py`, `.env.example`, `requirements.txt`, `.gitignore` | New paths and collection name; documented variables; dependencies pinned (`mcp`, `langfuse`), `pytest` added; cache and runtime database ignored |
| `frontend/src/app/app.routes.ts`, `app.component.ts`, `styles.scss` | Tier-1 routes (`/` is the chat for every user; operations routes use the admin guard; `/ask-docs` redirects to `/`); new navigation, theme toggle and toast host; light theme and shared styles |
| `frontend/src/app/app.component.spec.ts` | Replaced a scaffold spec that could not compile, which had blocked every Angular test |

## 5. Data model (`data/tier1.db`)
Ten tables, drawn in `deliverables/week12/diagrams/entity_diagram.mmd`: `customers`, `orders`, `tickets` (also carries the eval
ground truth, which the API never returns), `ai_results`, `decisions`, `ticket_feedback`, `handoffs`, `spans`, `jobs`, `meta`.
The file is git-ignored and seeded from the synthetic data, so the tracked `data/app.db` is never touched.

## 6. Configuration
Documented in `.env.example`: `LLM_MODEL` (the code default `llama-3.3-70b-versatile` is not available on every key; set one yours
can reach), `JUDGE_MODEL`, `LLM_CACHE` (`readwrite`, `off` for production, `replay` for CI), `LLM_TPM`, `PII_HASH_SALT`,
`TIER1_DB_PATH`, `TIER1_AS_OF`, and the test-only `TIER1_ABLATE`.

## 7. How to run
```bash
make setup && make ingest        # install, generate the synthetic corpus, build the search index
make demo                        # answer a RANDOM ticket (the seed is printed)
python -m tier1 answer --ticket TK3000
python -m tier1 eval             # about 160,000 tokens; see the free-tier cap in section 9
python scripts/mcp_smoke.py      # call both MCP servers as an outside client would
# to show the UI to someone else, see the ngrok section of the root README.md
make api                         # FastAPI; then: cd frontend && npx ng serve --proxy-config proxy.conf.json
```

## 8. Tests
189 Python tests pass (3 older tests in `tests/test_structure_chunker.py` fail on a clean checkout too and are deselected) and 19
Angular specs pass in headless Chrome. The production Angular build passes. Coverage that matters most: the guards (including the
Unicode and padding cases), the gateway (cache, replay, retries, the daily-cap fail-fast), redaction, the API (permissions, masking,
the feedback-to-case loop), the assertions and runner arithmetic, and two integration tests that start the real MCP servers
with a scripted model and check one trace id across every hop and that no seeded email, address, name or id reaches any sink.

## 9. What the evidence says (read before quoting any number)
Full tables are in `deliverables/week12/eval/report_after.md`; the reasoning is in `taxonomy.md`, `weaknesses.md` and `seams.md`
(51 rows, each marked fixed, accepted or ran-out-of-time).

- **Full-system eval:** 33 of 39 pass; all 6 refund-policy cases pass (3 of 3 question pairs right for both customers).
- **Wrong refund policy:** the final-answer rate did NOT move. With the version filter and policy guard off it was 0 of 10, the same as
  on. Only retrieval exposure moved: 78% to 0% of top-3 results containing the wrong version (60 refund tickets, offline). The guard is
  insurance this sample cannot show is needed.
- **Real failures found:** 5 of 25 answerable cases cited the wrong source (near-duplicate sibling articles, one internal macro).
  Model output contains invisible and lookalike characters in 24 of 39 replies; that broke the guards and is the failure mode the
  integration created (it blocked a correct answer, and later a second form with padded brackets).
- **Closed loop:** two fixes were made (macros out of customer search; the error code in the search query). On 15 held-out tickets,
  on a second model, 6 pass without them and 8 with them, but 4 cases improved and 2 got worse: INCONCLUSIVE. The full re-run on the
  production model was cut off by the provider's daily cap.
- **Bonus pair:** deflection 76% (19 of 25 answerable), simulated re-open 60% (6 of 10); the human-reply control re-opened 4 of 5, so the
  method cannot separate good replies from poor ones at this size. A first version that scored 100% was flawed and is kept, not quoted.
- **Capacity:** the free tier caps this model at 200,000 tokens a day (about 40 tickets), against 67 a day at today's volume. That limit is
  in no response header; it appeared as a 429 after a day of testing. See `cost_and_10x.md`.
- **Cost:** about $0.0016 per deflected ticket (all spend divided by deflected tickets), using a price table that is unverified.

## 10. Not done, and why
- **Judge agreement is not measured.** It needs a person who has worked a support queue to label replies on the admin page `/label` (stored in `evaluation/integrated/labels.json`);
  the report says "NOT MEASURED" until then.
- **The fresh-eyes review** by a reviewer from another squad has not happened (`deliverables/week12/fresh_eyes.md` is a template).
- **A clean full re-run of the fixed system** on the production model (daily token cap).
- **Not built:** undo after approve or escalate, Angular CDK focus trapping (done by hand), Playwright end-to-end tests, a request queue
  for load, built Docker images and a CI run (the files are written and syntax-checked; the Docker daemon was not running).
- **Limits of the data:** everything is synthetic and templated, single-turn, and the entitlement tool is assumed correct.
- Nothing is committed; the work is in the `week12-capstone` worktree.

## 11. Where to look next
`deliverables/week12/README.md` is the index of every deliverable and the command that regenerates it; `deliverables/week12/demo_script.md`
is the 10-minute demo with the hostile questions answered from the files above.

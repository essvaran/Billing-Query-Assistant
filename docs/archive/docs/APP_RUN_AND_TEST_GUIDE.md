# Tier-1 Deflection Assistant: run, features, testing in the UI, and what comes next

This guide covers four things: how to run the app on your machine, what it does, how to see each feature in the
browser, and what still needs to be built or done. For a step-by-step guide by role, see `docs/USER_GUIDE.md` (also
in the app under **Help**).

All customer, order and ticket data is synthetic. Every evaluation number comes from a stored run. A number that has
not been measured shows as **Not measured**.

---

## 1. How to run the app locally

### What you need

| Tool | Version | Why |
|---|---|---|
| Python | 3.12 | API, assistant, MCP servers, evaluation |
| Node.js | 22 | Angular web app |
| A Groq API key | free tier is enough | the language models |
| make (optional) | any | short commands; Windows can use `./tasks.ps1` instead |

### Step 1: one-command setup

```bash
python -m venv .venv
```

```bash
source .venv/bin/activate
```

On Windows, activate with `.venv\Scripts\activate` instead.

```bash
make up
```

On Windows without make, run `./tasks.ps1 up`. Without either, run `python -m tier1 up`.

On the first run, `.env` is created from `.env.example` and the command stops, listing the values to fill in:

| Key | What to put |
|---|---|
| `GROQ_API_KEY` | your Groq key |
| `JWT_SECRET` | a random string of 32 or more characters |
| `ADMIN_EMAIL` | the email that signs in as team lead (admin) |

Run `make up` again. It checks the key and which models it can reach, installs packages, generates the synthetic
data, builds the search index, loads the ticket database, creates the catalog database (`data/catalog.db`) from
`data/seed/`, and answers one random ticket. Each stage prints OK, SKIP (already done) or FAIL with the fix, so a
re-run is safe.

### Step 2: start the API (terminal 1)

```bash
make api
```

The API runs on http://localhost:8000. Two checks:

- http://localhost:8000/api/health: the process is up.
- http://localhost:8000/api/ready: the configuration is valid, the databases open, and the search index is present.

### Step 3: start the web app (terminal 2)

```bash
cd frontend
```

```bash
npm ci
```

```bash
npx ng serve --proxy-config proxy.conf.json
```

Open http://localhost:4200.

### Step 4: sign in

- **Team lead (admin):** sign in with the `ADMIN_EMAIL` account (Google, or email and password if enabled). You
  see every page.
- **Customer (user):** sign up with any other email. You see Chat, Account and Help only. A customer is matched to
  synthetic customer data by email. For a demo, set `TIER1_DEMO_CUSTOMER_ID` in `.env` (never in production).

### Optional: containers

```bash
docker compose up --build
```

Then open http://localhost:8080. Compose runs the API in production mode, which refuses to start on unsafe settings
and names each fix. The images have not been built on the development machine yet (see section 4).

### Useful commands

| Command | What it does |
|---|---|
| `python -m tier1 demo` | answers a random ticket and prints the seed so the draw can be repeated |
| `python -m tier1 answer --ticket TK3000` | answers one ticket |
| `python -m tier1 eval --tag NAME` | runs the integrated evaluation suite (`--resume` continues after the daily limit) |
| `python -m tier1 eval --rescore NAME` | recomputes a report and judge agreement with no model calls |
| `python -m tier1 eval --cases regression` | runs only the cases created from wrong-answer reports |
| `python scripts/mcp_smoke.py` | talks to both MCP servers the way an outside client would |
| `make mcp-http` | serves the help-centre MCP server over HTTP on port 8765 (needs `MCP_HTTP_TOKEN` in `.env`) |
| `python -m pytest tests -q` | backend tests |
| `cd frontend` then `npx ng test --watch=false` | frontend tests |

### Where configuration lives

- **`.env`:** secrets and deployment wiring only (keys, `JWT_SECRET`, database paths such as `APP_DB_PATH`,
  `TIER1_DB_PATH`, `CATALOG_DB_PATH`).
- **Catalog database (`data/catalog.db`):** everything else, edited on the admin **Data** page. It is created from
  `data/seed/` on first start and never overwritten by a restart. To start again from the seed files, stop the app
  and delete `data/catalog.db`.

### Free-tier limits you will meet

The free Groq tier allows about 8,000 tokens a minute and 200,000 tokens a day for the agent model. That is about 60
tickets a day. When the daily limit is reached, the assistant hands tickets to a person (reason "rate limited"), and
an evaluation run stops and saves its progress so `--resume` can continue it the next day.

---

## 2. Features available

### Customers (any signed-in user)

| Feature | Summary |
|---|---|
| Chat, Agent mode | answers questions about the customer's own account: it checks entitlement and order data through MCP tools discovered at runtime, cites help-centre articles with the policy version, and hands off to a person when unsure |
| Chat, Docs mode | searches the help centre and answers with citations; refuses when the corpus has no answer |
| Hand-off to a person | a plain-language message explains that a person will follow up |
| Answer feedback | thumbs up or down with a reason, plus a "report wrong answer" option |
| Onboarding and plan choice | on first sign-in |
| Account | plan, add-ons, subscription and invoices |
| Help | the user guide, filtered to the customer's role |

### Support agents and team leads (admin)

| Feature | Summary |
|---|---|
| Ticket queue | status tabs, search, filters stored in the address, keyboard shortcuts |
| Ticket workspace | runs the assistant with live steps, Entitlement card, source passages, then approve, edit, run again, escalate or report a wrong answer; blocks a refund or delivery draft that has no entitlement check |
| Trace view | every step of one run, with timing, tokens and cost |
| Try a ticket | runs the assistant on a random sample ticket or on your own text without touching real tickets |
| Escalations | waiting and claimed hand-offs, with what was already checked |
| Insights | quality figures from the latest evaluation, live traffic figures, the review inbox and the evaluation tab |
| Closed failure-to-test loop | a wrong-answer report becomes a regression case (REG01, ...) that runs in every evaluation |
| Label replies | a person labels replies Good or Not good (the judge's verdict is hidden); judge agreement is shown once 20 replies are labelled |
| Data page | create, edit and delete everything the app runs on (see below), with a change log |
| Admin | users, billing, documents, observability, and the earlier weeks' pages |
| Help | the whole user guide |

### The Data page (admin)

| Section | What you can change |
|---|---|
| Reference lists | every drop-down and label (about 40 lists: escalation reasons and their customer messages, regions, plans, refund policy versions, statuses, failure modes, alert types and more) |
| Settings | runtime values with allowed ranges (models, token limits, budgets, retrieval sizes, alert thresholds, capacity-plan figures); shows when an environment variable overrides a value |
| Model prices | USD per million tokens, used by every cost figure |
| Prompts | every prompt, versioned; a new version must pass a test gate before it can go live |
| Guard rules | the patterns that block hostile or out-of-scope tickets, versioned; every version must pass the stored examples |
| Eval cases | the cases each evaluation runs, by suite; switch a case off without deleting it |
| Eval runs | stored runs with pass counts; keep notes, delete old runs |
| Customers, Orders, Tickets | the Tier-1 data the assistant answers from, with integrity checks |
| Change log | who changed what, when, with the value before and after |

### Admin page tabs

| Tab | Summary |
|---|---|
| Tickets, Orders, Customers | the Week 7 agent's data |
| Documents | upload a file (.pdf, .md, .txt, .docx, .xlsx) to make it searchable in Docs mode |
| Users | promote, demote, disable, re-enable |
| Billing | dashboard, plans, add-ons, subscriptions, invoices |
| Observability | traces and support drill, user feedback, cost and 10x calculator, email alerts, failure-to-test runs |
| Traces, Sample, Taxonomy | Docs-mode trace list, trace sample and replay, failure taxonomy |
| Eval | the Week 6 evaluation, computed from stored rows |
| Race, Trajectory, Multi-Agent | Week 7 to 10 experiments: single agent against a fixed workflow, tool-sequence evaluation, multi-agent runs |

### Outside the web app

- **Two MCP servers** (`mcp_servers/`): Tier-1 tools and the help centre. The help-centre server can also run over
  HTTP with a bearer token, so another squad's client can call it (see `docs/MCP_CLIENT_GUIDE.md`).
- **Tracing** across the agent and MCP hops, with personal data redacted (Langfuse, optional).
- **Cost and 10x report:** `scripts/cost_and_10x.py`, written to `deliverables/week12/cost_and_10x.md`.

---

## 3. How to test (view) each feature in the UI

Sign in as the admin account unless a step says otherwise. Steps marked **uses quota** call the language model.

### Customer view

Sign in with a non-admin email. For a demo, set `TIER1_DEMO_CUSTOMER_ID` first.

| Feature | Steps | What you should see |
|---|---|---|
| Onboarding | sign in with a new account | the plan picker; after choosing, the Chat page |
| Agent mode (**uses quota**) | Chat, keep **Agent**, ask "Can I get a refund for my last order?" | the steps as they run, then a reply with numbered sources naming the policy version, or a hand-off message |
| Docs mode (**uses quota**) | switch to **Docs**, ask "How do I update my card?" | an answer with citations; a question the help centre does not cover gets the refusal message |
| Feedback | thumbs down on an answer and pick a reason | a confirmation; as admin, the report appears in Insights, Review inbox |
| Account | open **Account** | plan, add-ons and invoices |
| Role filtering | open **Help** | only the customer sections; team-lead pages show a 403 page if typed into the address bar |

### Team lead: ticket work

| Feature | Steps | What you should see |
|---|---|---|
| Queue | **Tickets**; press `/`, type "refund"; use the policy and region filters | the list narrows; the address keeps the filters |
| Workspace (**uses quota**) | open a ticket, click **Run the assistant** | live steps, then a draft or an escalation with a reason; the Entitlement card shows the policy and whether the order is inside the refund window |
| Sources | click a source chip | the drawer opens with the cited passage highlighted |
| Decisions | edit the draft, then **Approve and copy** (Ctrl+Enter) | the decision is recorded as edited; the ticket moves to Approved |
| Escalation | **Escalate** (Shift+E) | the ticket appears in **Escalations**, Waiting |
| Trace | **Open full trace** | every step with time, tokens and cost |
| Try a ticket (**uses quota**) | **Try a ticket**, pick an example chip (the legal threat or injection attempt) | the guard escalates before any model call, with the reason |
| Escalations | **Escalations**, **Claim**, then **Mark resolved** | the card moves from Waiting to Claimed to resolved |
| Act as customer | Chat, open the **Act as customer** picker | customers grouped by refund policy; answers use that customer's account |

### Team lead: quality loop

| Feature | Steps | What you should see |
|---|---|---|
| Insights | **Insights**, Overview | quality figures from the latest run; anything unmeasured says **Not measured** |
| Report to test (**uses quota**) | Workspace, **Report wrong answer**; then Insights, Review inbox, **Create evaluation case**, **Run this test** | a new REGnn case; the Evaluation tab shows pass or fail per check, with a trace link |
| Labelling | **Label replies**; enter your name; label with G, N or S | one reply at a time, no judge verdict; after 20 labels, **Check agreement** shows each judge's agreement with you |
| Week 6 evaluation | **Admin**, Eval tab (or `/eval`) | cases, failure modes and judge agreement computed from stored rows (prompt v1 24/25, v2 20/25) |

### Team lead: Data page

| Feature | Steps | What you should see |
|---|---|---|
| Relabel a value | **Data**, Reference lists, Refund policy versions, **Edit** a label, save; open Data, Customers | the new label on every customer using that policy |
| Protected values | Reference lists, Escalation reasons, try to delete `rate_limited` | refused: built-in values can be relabelled only |
| Settings | Settings, change a value outside its range | refused with the allowed range; **Reset** returns the default |
| Prompt gate | Prompts, edit a copy, add `{{unknown_thing}}`, **Save as draft** | saved as **rejected**, with the failing check listed; it cannot be activated |
| Prompt versions | save a valid draft, **Activate** it, then **Restore** the older version | the active version changes; the old one stays restorable |
| Guard rules | Guard rules, **Add example** with text that should be blocked | a warning if the live rules do not catch it yet; a new version must pass every example |
| Eval cases | Eval cases, pick a suite, **Switch off** a case | the case stays listed but greyed out and is left out of runs |
| Tier-1 data | Orders, **Add order** with a customer id that does not exist | the form stays open with "Customer ... not found"; with a real customer it saves |
| Integrity | Customers, **Delete** a customer that has orders | refused, naming how many orders remain |
| Change log | Change log, filter by kind | each edit above with who, when, and before and after values |

### Team lead: Admin page

| Feature | Steps | What you should see |
|---|---|---|
| Users | Admin, Users, demote or disable a test account | the change applies on that user's next click |
| Billing | Admin, Billing | dashboard figures; create a plan; mark an invoice paid |
| Documents | Admin, Documents, upload a small .md file; ask about it in Docs mode | the file becomes searchable |
| Observability | Admin, Observability | tabs for traces and support drill, user feedback, cost and 10x, email alerts, failure to test |
| Earlier weeks | Admin, the Traces, Sample, Taxonomy, Race, Trajectory and Multi-Agent tabs | the Week 5 to 10 pages; **Run Race** uses quota and takes 3 to 5 minutes |

### Checks from the browser address bar

- http://localhost:8000/api/ready returns ready when the app can answer tickets.
- http://localhost:8000/api/docs lists every API endpoint (FastAPI's interactive docs).

---

## 4. Future enhancements needed

### Needs a person (cannot be done by the code)

1. **Label 20 or more replies** on **Label replies**. Until then, judge agreement is not measured and the 85%
   requirement cannot be shown.
2. **Choose the judge rubric.** The stored Week 6 rows give prompt v1 96% and prompt v2 80% agreement. The integrated
   evaluation's main judge uses v2. Decide whether to switch to v1, or to keep v2 and re-validate it on the new labels.
3. **Fresh-eyes review** by another squad (`deliverables/week12/fresh_eyes.md`), **adopt and date**
   `deliverables/week12/weaknesses.md`, and **deliver the live demo**.

### Capacity and quality

4. **Lift the daily token limit** (paid tier or a second provider). It caps the system at about 60 tickets a day,
   below today's volume, and stopped full evaluation runs part way.
5. **Re-run the full suite on the production model** once the limit allows, so the before and after of the source
   fixes is measured on the whole suite. The held-out comparison so far is inconclusive.
6. **Retrieval:** the wrong article is picked often enough to matter (weakness 2). Try a re-ranker or better chunking
   of error-code articles.
7. **Prove the cheaper path:** the prefetch saved 25% of tokens but scored 7 of 10 against 8 of 10. Run a larger
   comparison.
8. **Stronger PII redaction:** it is pattern- and list-based today; a named-entity model would catch first names,
   misspellings and unusual addresses.
9. **Multi-turn and real data:** everything is single-turn and synthetic. Measure re-opens and real help-centre
   language before trusting the numbers in production.

### Production hardening

10. **Build and run the Docker images** and **run CI** on a real runner. The files are written and validated, but
    there was no Docker daemon on the development machine.
11. **Database and queue:** SQLite was kept on purpose for a demo-grade build. For real traffic, move to Postgres and
    put ticket runs on a job queue.
12. **HTTPS** in front of the API (reverse proxy), and a secret store instead of `.env`.
13. **Customer identity:** customers are matched to account data by email; a real deployment needs the account
    system's own ID mapping, and `TIER1_DEMO_CUSTOMER_ID` must stay unset.

### Product and UI

14. **Undo for 5 seconds** after approve or escalate (needs a decision-delete endpoint).
15. **End-to-end browser tests** (for example Playwright). Behaviour is covered by API tests, component specs and
    manual browser checks only.
16. **Form editor for eval cases:** cases are edited as JSON on the Data page; a field-by-field form would be safer.
17. **Approval workflow for the Data page:** edits apply at once; a second reviewer for prompt and guard activations
    would add a safety step.
18. **Tidy up:** three chunker tests fail on the committed code (they expect Markdown articles; the folder holds PDFs);
    the Week 7 `agent-chat` component is no longer routed; a few em dashes remain in older `api/*.py` files.
19. **Accessibility:** move the hand-written focus trap in the modal and drawer to Angular CDK and run an automated
    accessibility check.

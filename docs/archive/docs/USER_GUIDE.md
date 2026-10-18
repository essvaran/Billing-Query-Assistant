# Tier-1 Support Assistant: user guide

## Start here

The Tier-1 Support Assistant answers routine customer questions (refunds, delivery times, order status, account
how-tos) from the help centre and from your account, and hands everything else to a person. Every answer names the
help-centre article it used, and for refunds it names which refund policy applies to you (the 30-day policy or the
14-day legacy policy).

All customer data, orders and tickets in this installation are **synthetic**. No card is ever charged.

| You are | You sign in as | You can use |
|---|---|---|
| A customer | Your own account (email and password, or Google) | Chat, Account, Help |
| A support agent or team lead | An account with the admin role | Everything a customer has, plus Tickets, Escalations, Try a ticket, Insights, Label replies and Admin |
| An operator or developer | Not an app role: you have the code and the `.env` file | Setup, command line, evaluation, Docker, health checks |
| A reviewer from another squad | Not an app role: you connect an MCP client | The help-centre search tool |

### Signing in

1. Open the app. You land on the sign-in page.
2. Choose **Sign in** if you have an account, or **Create account** to make one (full name, email, and a password of
   at least 8 characters). If your organisation set up Google sign-in, you can use **Sign in with Google** instead.
3. A session lasts 7 days. When it ends you are sent back to the sign-in page with a message saying so.

Use the **Light/Dark** button in the header to switch themes. **Help** in the header opens this guide, showing the
sections for your role.

## Customers: asking a question

<!-- roles: user -->

The chat is the first page after you sign in. It has two modes, chosen in the bar under the message box.

### Agent mode (default): questions about your own account

1. Type your question, for example "Can I still get a refund for my last order?", and press **Enter**
   (**Shift+Enter** adds a new line).
2. While it works you see each step: checking your entitlement, looking up the order, searching the help centre.
   A first question can take up to a minute when the service has just started.
3. The reply arrives with numbered markers such as **[1]**. The **Sources** list under the reply names each
   article, and for refund questions it says which policy applies to you, for example "30-day policy".
4. Click a source to open it. The passage the assistant used is highlighted. A banner marks the retired 14-day
   policy, which still applies to some older accounts.
5. **Copy reply** copies the text.

The assistant works only on your own account. It cannot see other customers, and it cannot issue a refund itself:
it tells you what the policy says and whether your order is inside the window, and a person confirms the refund.

### When the assistant hands you to a person

Some questions always go to a person: anything about legal action, safety, fraud, an unrecognised charge or a
chargeback, questions outside Tier-1 support, and cases where the help centre has no reliable answer. You will see:
"I could not answer this safely, so I passed it to our team. A person will follow up." You do not need to ask again.

When the assistant is very busy, it also passes your question to the team instead of making you wait.

### Docs mode: general questions about the help centre

Switch to **Docs** to ask a general question. The answer shows a **Sources** list you can expand. If nothing
relevant exists, it says so instead of guessing.

### Telling us an answer was wrong

- In Agent mode, click **Report wrong answer** under a reply, choose a reason (wrong policy, wrong facts, should have
  passed to a person, should have answered, tone), add a note if you like, and send. The support team reviews every
  report.
- In Docs mode, use the thumbs. A thumbs-down asks for a reason.

## Customers: plan, billing and invoices

<!-- roles: user -->

### Choosing a plan (first sign-in)

New accounts go through three short steps before the chat:

1. **Choose a plan.** Switch between monthly and annual prices, pick Standard, Premium or Enterprise, and set the
   number of seats. The plan sets your refund window (Standard: 14 days; Premium and Enterprise: 30 days).
2. **Billing profile.** Company (optional), billing email, address and region.
3. **Add-ons and review.** Tick any add-ons, check the total, and click **Confirm and start**.

### The Account page

Open **Account** in the header to:

- see your plan, billing cycle, seats, renewal date and refund window;
- **Change plan** (unused time on the old plan is credited on the new invoice);
- edit your billing profile;
- read your invoices (number, date, period, amount, status);
- **Cancel subscription**. After cancelling, the next visit to the chat takes you back to plan selection.

A brand-new account has no orders yet, so questions about a specific order cannot be answered for it.

## Support agents: the ticket queue and workspace

<!-- roles: admin -->

### Ticket queue (Tickets)

- Status tabs with counts: All, New, Draft ready, Escalated by assistant, Approved, Escalated.
- Search the subject or text; filter by refund policy and region. Filters are kept in the address, so a filtered
  view can be bookmarked or shared.
- Keyboard: **j** and **k** move, **Enter** opens, **/** searches, **?** lists the shortcuts.

### Working a ticket

1. Open a ticket. The left pane shows the ticket, the customer and the **Entitlement** card (policy, refund window,
   plan, region, delivery times, and whether the order is inside the refund window).
2. Click **Run the assistant**. You see each step live. The result is either a draft or an escalation with a reason.
3. Check the draft against the Entitlement card. Click a source chip to read the passage it cites.
4. Then choose one:
   - **Approve and copy** (Ctrl+Enter): copies the reply and records your decision. If you edited the text first, it
     is recorded as edited, which feeds the edit-rate metric.
   - **Edit** (E), then approve.
   - **Run again** (R).
   - **Escalate** (Shift+E): writes a handoff note and puts the ticket in the escalation queue.
   - **Report wrong answer**: sends the draft to the team lead's review inbox.
5. A refund or delivery draft without an entitlement check is blocked: Approve stays off and a red alert explains why.

**Open full trace** shows every step the assistant took, with time and cost.

### Acting as a customer in the chat

In the chat, admins get an **Act as customer** picker, grouped by refund policy, to see exactly what a given
customer would get.

### Try a ticket

**Try a ticket** runs the assistant without touching a real ticket: draw a random sample ticket (the seed is shown so
the same draw can be repeated) or write your own with a customer and optional order. Example chips cover a refund
question, a delivery time, a password reset, a legal threat and an injection attempt.

## Support agents: escalations

<!-- roles: admin -->

**Escalations** lists tickets the assistant would not answer and tickets agents handed over.

1. The **Waiting** tab shows unclaimed handoffs with the reason and a summary of what was already checked, so nobody
   repeats the work.
2. Click **Claim** to take one. It moves to **Claimed** with your name.
3. Open the ticket from the card, reply to the customer, then click **Mark resolved**.

## Team leads: quality, review inbox and regression tests

<!-- roles: admin -->

Open **Insights**.

### Overview

Quality figures from the latest evaluation run (cases passing every check, wrong-policy citations, both refund
policies, judge agreement, cost per deflected ticket) and live traffic figures (answered, escalated, edited, cost,
time to draft). Anything that has not been measured says **Not measured**; no number is ever made up. The
"Where it fails" table links each failure mode to a trace.

### Review inbox: turning a failure into a permanent test

1. Reports from agents and customers appear in **Review inbox**.
2. Read the report and open its trace.
3. Click **Create evaluation case**. The failure becomes a regression case (REG01, REG02, ...) that runs in every
   future evaluation, so it stays guarded after it is fixed.
4. Click **Run this test**. The Evaluation tab shows the case **passes** or **fails**, each check marked Pass or Fail
   (failures first), with a link to the new trace.
5. After a fix, click **Run this test** again and confirm it now passes.

### Evaluation tab

- **Run regression cases** runs only the cases created from reports (fast).
- **Run the full suite** runs all cases. It takes 20 to 30 minutes and uses model quota, so it asks first.
- If the run stops because the provider's daily limit was reached, the page says so. The operator can continue the
  same run the next day (see Operators: evaluation).

## Team leads: labelling replies

<!-- roles: admin -->

The evaluation uses an automatic judge to grade replies. **Label replies** is where a person checks that judge.
The brief requires the judge to agree with a person on at least 85% of at least 20 replies.

1. Open **Label replies**. If there are several evaluation runs, pick one at the top (the newest is selected).
2. The first time, enter your name and your support-queue experience. They are stored with the labels.
3. For each reply you see the ticket, the account facts (Entitlement card and order record), the reply exactly as
   the customer would get it, and the sources the assistant had. Click a source to read it.
4. Decide: would a Tier-1 lead send this reply as written? Correct for this customer's policy and order, nothing
   invented, answers the question, and never says a refund has been issued.
   - **Good** (key **G**), **Not good** (key **N**), or **Skip** (key **S**).
   - **Previous** goes back to change a label.
5. The judge's verdict is never shown on this page, so it cannot influence you.
6. After 20 labels, **Check agreement** shows how often each judge agreed with you, and how many times the judge
   said GOOD where you said NOT GOOD (the dangerous kind of disagreement).
7. Tell the operator, who refreshes the report with `python -m tier1 eval --rescore <run>`.

A label belongs to the exact reply you read. If a later run gives a different reply to the same ticket, that reply
needs its own label.

## Team leads: users, plans and billing

<!-- roles: admin -->

Open **Admin**.

- **Users:** promote a user to admin or demote them, and disable or re-enable an account. Changes take effect on the
  user's next click, not when their session ends. The primary admin cannot be demoted or disabled.
- **Billing:** a dashboard (subscribers, recurring revenue, sign-ups, cancellations, open invoices); plans (create,
  edit, archive; changing a price affects only future invoices; the refund policy and refund days of a plan decide
  what the assistant tells its subscribers); add-ons; subscriptions (set a plan, add a charge); invoices (mark paid or
  void an open invoice).
- **Documents:** upload a file (.pdf, .md, .txt, .docx, .xlsx, up to 20 MB) to make it searchable in Docs mode.
- **Observability:** trace search and the support drill, user feedback, cost and the 10x calculator, email alerts,
  and evaluation run comparison.

## Team leads: the Data page

<!-- roles: admin -->

Open **Data**. Everything the assistant and the app run on is stored in the catalog database and edited here; nothing
a person reads in a list, label, prompt, rule or default is typed into the code. Edits take effect within a few
seconds in every process (the API, the MCP servers, the eval), and each one is written to the change log with who
made it and the value before and after.

- **Reference lists:** every drop-down and label in the app (escalation reasons and the message the customer sees,
  regions, plans, refund policy versions, ticket statuses, order statuses, failure modes, alert types and more).
  Add, relabel, reorder, switch off or delete a value. Values marked **Built in** are codes the application relies
  on: they can be relabelled but not switched off or deleted. A value still used by stored records cannot be
  deleted; switch it off instead, and old records keep showing its label.
- **Settings:** runtime values with their allowed range (models, token limits, budgets, retrieval sizes, alert
  thresholds, capacity-plan figures). A setting that an environment variable overrides says so and shows the value
  in use. **Reset** returns it to the shipped default.
- **Model prices:** USD per million tokens, used by every cost figure. `default` prices any model that is not listed
  and cannot be deleted. Record where and when you checked a price.
- **Prompts:** every prompt the system sends, versioned. Edit a copy, **Check** it, then **Save as draft**. A draft
  must pass the test gate (length, required placeholders present, no unknown placeholders, required phrases, plain
  ASCII) before it can be activated; a draft that fails is kept as **rejected** so you can see why. Activating a
  version retires the previous one; a retired version can be restored.
- **Guard rules:** the patterns that stop hostile or non-Tier-1 tickets before any model call, and the checks on a
  draft after it. Same draft, test and activate cycle as prompts. The test runs every stored example: each must be
  caught by the expected category (or pass, or match the expected post rule). Add an example whenever a ticket slips
  through; the page tells you if the live rules do not handle it yet. The last example of a category cannot be
  deleted, so every category stays tested.
- **Eval cases:** the cases every evaluation run uses, by suite (main, held-out, regression, Docs). Edit the fields
  as JSON; the server checks every code against the reference lists. **Switch off** keeps a case but leaves it out
  of runs.
- **Eval runs:** stored runs with their pass counts. Keep notes on a run or delete one. Runs are created by the
  evaluation, not here.
- **Customers, Orders, Tickets:** the Tier-1 data the assistant answers from. A customer with orders, or an order
  with tickets, cannot be deleted until its dependents are; a ticket's order must belong to its customer.
- **Change log:** every edit above, newest first, filterable by kind.

Lists come from the server when you sign in and after every navigation, so a relabel shows on the other pages on
your next click.

## Operators and developers

<!-- roles: admin -->

### One command from a fresh clone

You need Python 3.12 and a free Groq API key. Then:

```bash
make up
```

On Windows without make: `./tasks.ps1 up`. Without either: `python -m tier1 up`.

The first run creates `.env` from `.env.example` and stops, listing what to fill in: `GROQ_API_KEY`, `JWT_SECRET`
(a random string of 32 or more characters) and `ADMIN_EMAIL`. Run the command again. It checks the key and the
models it can reach, installs packages, generates the synthetic data, builds the search index, loads the ticket
database and answers one random ticket. Each step prints OK, SKIP (already done) or FAIL with the fix, and a second
run skips what is done.

Start the web app:

```bash
make api
cd frontend && npm ci && npx ng serve --proxy-config proxy.conf.json
```

Open http://localhost:4200. Or run everything in containers with `docker compose up --build` and open
http://localhost:8080.

### Where configuration lives

Secrets and deployment wiring stay in `.env` (keys, `JWT_SECRET`, database paths). Everything else is in the
catalog database `data/catalog.db` (`CATALOG_DB_PATH` to move it) and is edited on the Data page. On first start the
catalog is created from `data/seed/` (reference lists, settings, prices, prompts, guard rules, Week 7 data) and the
eval files are imported once. After that the seed files are never read again for data that exists, so an edit or
a delete in the app is not undone by a restart. A setting whose environment variable is set (for example
`LLM_MODEL`) uses the environment value; the Data page shows that it is overridden. To start again from the seed
files, stop the app and delete `data/catalog.db`.

### Command line

| Command | What it does |
|---|---|
| `python -m tier1 demo` | Answer a random sample ticket; prints the seed (`--seed N` repeats a draw) |
| `python -m tier1 answer --ticket TK3013` | Answer one sample ticket |
| `python -m tier1 answer --text "..." --customer C1000 --order O2099` | Answer free text as a customer |
| `python -m tier1 handoffs` | List queued escalations |
| `python -m tier1 eval` | Run the integrated evaluation (all cases, both judges) |
| `python scripts/mcp_smoke.py` | Call both MCP servers the way an outside client would |
| `python -m pytest tests -q` | Run the tests (no model calls) |

### Evaluation

- `python -m tier1 eval --tag fix1` runs every case and writes `deliverables/week12/eval/report_fix1.md`.
- The free tier allows about 200,000 tokens a day. If a run reaches the limit it stops, saves the finished cases,
  and prints the command to continue: `python -m tier1 eval --tag fix1 --resume` (same flags as the first run).
- `python -m tier1 eval --rescore fix1` recomputes the report and judge agreement from saved results without any
  model call. Run it after people label replies.
- `--cases regression` runs only the regression cases; `--case-id REG01` runs one case; `--no-judge` skips the
  judges; `--ablate prefetch` (or `version_filter`, `policy_guard`, `macro_filter`, `error_code_prompt`) switches one
  defence off to measure what it is worth. Never set `TIER1_ABLATE` in production.

### Health and readiness

- `GET /api/health` returns `{"status": "ok"}` while the process runs.
- `GET /api/ready` returns 200 when the configuration is valid, both databases open and the search index exists;
  otherwise 503 with a list of problems and their fixes. Docker uses it as the health check.

### Running in production

Set `APP_ENV=production`. The API then refuses to start, with a message naming each fix, if:

- `JWT_SECRET` is missing, an example value, or shorter than 32 characters;
- `LLM_CACHE` is not `off` (the response cache would keep customer text on disk);
- `TIER1_DEMO_CUSTOMER_ID` is set (every user would act as the same customer);
- `PII_HASH_SALT` is still the example value.

### Privacy rules

- Customer emails, names and addresses are removed from traces, logs, the MCP wire log and Langfuse. Customer and
  order ids are replaced by salted hashes.
- Limits: a first name on its own, a misspelt name, an unusual address format or a number written in words can get
  through. Do not put real customer data into this synthetic installation.

### Limits you will meet

- Free tier: about 8,000 tokens a minute and 200,000 a day for the agent model. Back-to-back tickets queue, and a busy
  assistant hands tickets to a person.
- At most two tickets run at once in the API; a third is told the assistant is busy.
- The first ticket after a start takes about 15 seconds longer while the search model loads.

## Reviewers from another squad: calling the MCP server

<!-- roles: admin -->

The help-centre search is exposed as an MCP server with one tool, `search_help_centre`. Follow
`docs/MCP_CLIENT_GUIDE.md`, using your own MCP client, and write down where you got stuck in
`deliverables/week12/fresh_eyes.md`. Please do not ask the author for help while you try: the point is to find what
the guide leaves out.

## Troubleshooting

| What you see | What it means | What to do |
|---|---|---|
| "This page is for the support team" | Your account does not have the admin role | Ask your team lead to promote your account in Admin, Users |
| Sent back to the sign-in page | Your session ended (7 days) or your account was disabled | Sign in again; if it fails, contact your team lead |
| "The assistant is very busy" or a ticket passed to a person right away | The model provider's usage limit was reached | Nothing to do as a customer; operators see Limits you will meet |
| A source opens without a highlighted passage | The cited passage could not be located in the article text | Read the article; report the answer if it does not support the reply |
| Agreement stays locked on Label replies | Fewer than 20 replies are labelled in that run | Keep labelling |
| `make up` stops at .env | Values are missing or still the examples | Fill them in as the message says and run it again |
| `GET /api/ready` returns 503 | Configuration or data problem | Read the `problems` list in the response; each has a fix |

## Glossary

| Term | Meaning |
|---|---|
| Entitlement | What this customer is entitled to, from the account system: plan, refund policy, refund window, delivery times |
| Refund policy version | `refund-30d` (current) or `refund-14d` (legacy, still applies to some older accounts) |
| Escalation, handoff | A ticket passed to a person, with the reason and what was already checked |
| Deflected ticket | A ticket answered correctly without a person writing the reply |
| Trace | The record of one ticket from question to answer: every step, its time and cost |
| Regression case | A test created from a reported failure; it runs in every future evaluation |
| Judge | A second AI model that grades replies; trusted only as far as it agrees with a person |

# Tier-1 Support Assistant: functional README

What the app does for each kind of user, how to use it, how to see each feature in the browser, and what is not done yet. Setup, architecture and code are in the technical README, [README.md](README.md). The app's **Help** page shows this file, filtered to your role.

## Start here

The Tier-1 Support Assistant answers routine customer questions (refunds, delivery times, order status, account
how-tos) from the help centre and from your account, and hands everything else to a person. Every answer names the
help-centre article it used, and for refunds it names which refund policy applies to you (the 30-day policy or the
14-day legacy policy).

All customer data, orders and tickets in this installation are **synthetic**. No card is ever charged.

| You are | You sign in as | You can use |
|---|---|---|
| A customer | Your own account (email and password, or Google) | Chat, Account, Help |
| A support agent or team lead | An account with the admin role | Everything a customer has, plus Tickets, Escalations, Try a ticket, Insights, Label replies, Data and Admin |

### Signing in

1. Open the app. You land on the sign-in page.
2. Choose **Sign in** if you have an account, or **Create account** to make one (full name, email, and a password of
   at least 8 characters). If your organisation set up Google sign-in, you can use **Sign in with Google** instead.
3. A session lasts 7 days. When it ends you are sent back to the sign-in page with a message saying so.

Use the **Light/Dark** button in the header to switch themes. **Help** in the header opens this guide, showing the
sections for your role.

## Team view: what customers can do

<!-- roles: admin -->

Two more groups work with the app without an app role: **operators and developers** (they have the code and the
`.env` file: setup, command line, evaluation, Docker, health checks) and **reviewers from another squad** (they
connect an MCP client to the help-centre search tool). Their sections are at the end of this guide.

| Feature | Summary |
|---|---|
| Chat, automatic routing | the customer just asks; each question goes to the assistant or to the help articles, and the answer says which |
| Chat, assistant | answers questions about the customer's own account: it checks entitlement and order data through MCP tools discovered at runtime, cites help-centre articles with the policy version, and hands off to a person when unsure |
| Chat, help articles (Docs) | searches the billing help articles and answers with citations; refuses when the corpus has no answer |
| Hand-off to a person | a plain-language message explains that a person will follow up |
| Answer feedback | thumbs up or down with a reason, plus a "report wrong answer" option |
| Onboarding and plan choice | on first sign-in |
| Account | plan, add-ons, subscription and invoices |
| Help | the user guide, filtered to the customer's role |

### Seeing each feature

Sign in with a non-admin email. For a demo, set `TIER1_DEMO_CUSTOMER_ID` first.

| Feature | Steps | What you should see |
|---|---|---|
| Onboarding | sign in with a new account | the plan picker; after choosing, the Chat page |
| Assistant (**uses quota**) | Chat, ask "Can I get a refund for my last order?" | "Answered using your account", the steps as they run, then a reply with numbered sources naming the policy version, or a hand-off message |
| Help articles (**uses quota**) | Chat, ask "What does ERR-4032 mean?" | "Answered from the help articles" and an answer with citations; a question the articles do not cover gets the refusal message |
| Feedback | thumbs down on an answer and pick a reason | a confirmation; as admin, the report appears in Insights, Review inbox |
| Account | open **Account** | plan, add-ons and invoices |
| Role filtering | open **Help** | only the customer sections; team-lead pages show a 403 page if typed into the address bar |

## Customers: asking a question

<!-- roles: user -->

The chat is the first page after you sign in. You just ask; you never choose where the answer comes from.
Questions about your own orders, refunds, deliveries or account go to the assistant, which uses your account.
General questions, such as what a billing migration error code means, are answered from the help articles. A small
line at the top of each answer says which one answered.

If no customer account is linked to your sign-in, account questions are answered from the help articles, with a
note explaining why.

### Questions about your own account

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
chargeback, questions outside Tier-1 support, and cases where the help centre has no reliable answer. You will see a
message that matches the reason (for example "This is outside what I can help with here, so I passed it to our team.
A person will follow up."). You do not need to ask again.

A plain greeting such as "Hi" is not passed on: the assistant replies and asks what you need. Ordinary questions that
only share a word with these topics, such as a chargeback fee or fraud protection on payments, are answered normally.
If an order number cannot be found, the assistant still explains your policy and asks you to check the number.

When the assistant is very busy, it also passes your question to the team instead of making you wait. A system error
is retried once before the question is passed on.

### General questions: the help articles

A general question is answered from the help articles. The answer shows a **Sources** list you can expand. If
nothing relevant exists, it says so instead of guessing.

### Telling us an answer was wrong

- Under an assistant answer, click **Report wrong answer** under a reply, choose a reason (wrong policy, wrong facts, should have
  passed to a person, should have answered, tone), add a note if you like, and send. The support team reviews every
  report.
- Under a help-articles answer, use the thumbs. A thumbs-down asks for a reason.

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
customer would get. Admins also get a mode selector: **Auto** (the default, what customers get), **Agent** or
**Docs** to force one path while testing. Routing rules and the classifier prompt are in Admin, Settings (Chat
routing) and Admin, Prompts (Chat router).

Other signed-in customers see a label beside the message box, such as "Answers use your Standard plan", showing
the account the assistant uses. If no customer account is linked to the sign-in, it reads "Answers use the help
articles". With **Agent** forced, an admin with no customer chosen cannot send.

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
6. After 20 labels, **Check agreement** shows how often each of the three judges agreed with you, and how many times
   a judge said GOOD where you said NOT GOOD (the dangerous kind of disagreement). The **Primary judge** is the Week 6
   v1 rubric, the one that agreed with people 24 times out of 25 in Week 6. The two second opinions are the Week 6 v2
   rubric and the integrated rubric.
7. Tell the operator, who refreshes the report with `python -m tier1 eval --rescore <run>`. The 85% target counts
   only for the primary judge.

A label belongs to the exact reply you read. If a later run gives a different reply to the same ticket, that reply
needs its own label. Re-grading a run with new judges (`python -m tier1 eval --rejudge <run>`) does not change the
replies, so your labels still count.

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
  A PDF must contain real text: a scanned, image-only PDF is rejected with a message saying so.
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

## Team leads: every feature and how to see it

<!-- roles: admin -->

### Support agents and team leads

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
  HTTP with a bearer token, so another squad's client can call it (see section 8 of `README.md`).
- **Tracing** across the agent and MCP hops, with personal data redacted (Langfuse, optional).
- **Cost and 10x report:** `scripts/cost_and_10x.py`, written to `docs/archive/deliverables/week12/cost_and_10x.md`.

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

## Operators and developers

<!-- roles: admin -->

You run the app; this section is the short version. Details (configuration, architecture, data stores, APIs,
evaluation, Docker, CI) are in the technical README, `README.md`.

### Run it on your machine

You need Python 3.12, Node 22 and a free Groq API key.

```bash
make up
```

On Windows without make: `./tasks.ps1 up`. Without either: `python -m tier1 up`.

The first run creates `.env` and stops, listing what to fill in: `GROQ_API_KEY`, `JWT_SECRET` (32 or more random
characters) and `ADMIN_EMAIL`. Run the command again. It installs packages, generates the synthetic data, builds the
search index, loads the databases and answers one random ticket. Each step prints OK, SKIP (already done) or FAIL with
the fix.

Then start the API and the web app in two terminals:

```bash
make api
```

```bash
cd frontend && npm ci && npx ng serve --proxy-config proxy.conf.json
```

Open http://localhost:4200 and sign in with the `ADMIN_EMAIL` account. Or run everything in containers with
`docker compose up --build` and open http://localhost:8080.

### Health and readiness

- `GET /api/health`: the process is up.
- `GET /api/ready`: the configuration is valid, the databases open and the search index is present. A 503 lists each
  problem with its fix.

### Where configuration lives

Secrets stay in `.env`. Everything else (lists, settings, prices, prompts, guard rules, evaluation cases) is on the
**Data** page and stored in `data/catalog.db`. To start again from the shipped values, stop the app and delete
`data/catalog.db`.

### Limits you will meet

The free model tier allows about 200,000 tokens a day, about 60 tickets. When it is reached, the assistant hands
tickets to a person (reason "rate limited"), and an evaluation run stops, keeps what it finished, and continues the
next day with `python -m tier1 eval --tag <run> --resume`.

### Privacy rules

- Customer names, emails, addresses, phone and card numbers are removed before anything is logged or traced; customer
  and order ids are hashed.
- In production, set `APP_ENV=production` and `LLM_CACHE=off`, use a long random `PII_HASH_SALT`, and leave
  `TIER1_DEMO_CUSTOMER_ID` unset.

## Reviewers from another squad: calling the MCP server

<!-- roles: admin -->

The help-centre search is exposed as an MCP server with one tool, `search_help_centre`. There are two ways in:

- **Way A, over HTTP:** the author runs `make mcp-http` and sends you the URL and a bearer token separately. Connect
  with any MCP client that speaks Streamable HTTP (MCP Inspector, Claude Code, or your own code).
- **Way B, your own clone:** clone the repository, run `make up`, then start `mcp_servers/help_centre_server.py` from
  your own client over stdio.

The steps for both are in section 8 of the technical README (`README.md`, "MCP servers and outside clients"). Write down where you got stuck, and how long it took to get a first result, in
`docs/archive/deliverables/week12/fresh_eyes.md`. Please do not ask the author for help while you try: the point is
to find what the instructions leave out.

## What is not done yet

<!-- roles: admin -->

### Needs a person (cannot be done by the code)

In this order:

1. **Label 20 or more replies** of the newest full run (`fix1` today, `fix2` once it exists) on **Label replies**,
   ideally by someone who has worked a support queue. Until then, judge agreement is not measured and the 85% requirement cannot be shown. If the primary judge comes in
   under 85%, do not rewrite its rubric against the same labels: keep half the labels aside, change the rubric using
   the other half, and report both numbers.
2. **Adopt the weaknesses list:** read `docs/archive/deliverables/week12/weaknesses.md`, change what you disagree
   with, and keep your own date.
3. **Commit and push** the work, so that a fresh clone has everything described here.
4. **Fresh-eyes review** by another squad: they clone the repository, follow the technical README, and call the
   help-centre MCP server from their own client (see "Reviewers from another squad" above). They fill in
   `docs/archive/deliverables/week12/fresh_eyes.md`.
5. **Rehearse the 10-minute demo against a clock**, including the live loop on ticket TK3147 (case RAN02, still
   failing) in `docs/archive/deliverables/week12/demo_script.md` Part 3, then deliver it.

### Capacity and quality

6. **Re-run the whole suite with the response cache off** (run `fix2`, about a full day's token allowance), twice
   if possible, to measure how much results vary between runs. A cache-off rerun of 10 cases passed 4 where the
   current report's run passed 7, so today's pass rates are one draw. Label the new run's replies, not the old ones:
   a label belongs to the exact reply it was given for.
7. **Lift the daily token limit** (paid tier or a second provider). It caps the system at about 60 tickets a day,
   below today's volume, and stopped full evaluation runs part way.
8. **Retrieval:** the wrong article is picked often enough to matter (weakness 2). Try a re-ranker or better chunking
   of error-code articles. The source fixes helped on the cases they came from (6 to 3 wrong of 25) but the
   held-out comparison was inconclusive.
9. **Prove the cheaper path:** the prefetch saved 25% of tokens but scored 7 of 10 against 8 of 10. A
   second run with prefetch off (20 tickets, run `traj_off`) passed 16 of 20 at about 6,100 tokens per model ticket,
   against about 4,200 with prefetch on. Run a larger, repeated comparison on the same tickets.
10. **Stronger PII redaction:** it is pattern- and list-based today; a named-entity model would catch first names,
   misspellings and unusual addresses.
11. **Multi-turn and real data:** everything is single-turn and synthetic. Measure re-opens and real help-centre
    language before trusting the numbers in production.

### Production hardening

12. **Build and run the Docker images** and **run CI** on a real runner. The files are written and validated, but
    there was no Docker daemon on the development machine.
13. **Database and queue:** SQLite was kept on purpose for a demo-grade build. For real traffic, move to Postgres and
    put ticket runs on a job queue.
14. **HTTPS** in front of the API (reverse proxy), and a secret store instead of `.env`.
15. **Customer identity:** customers are matched to account data by email; a real deployment needs the account
    system's own ID mapping, and `TIER1_DEMO_CUSTOMER_ID` must stay unset.

### Product and UI

16. **Undo for 5 seconds** after approve or escalate (needs a decision-delete endpoint).
17. **End-to-end browser tests** (for example Playwright). Behaviour is covered by API tests, component specs and
    manual browser checks only.
18. **Form editor for eval cases:** cases are edited as JSON on the Data page; a field-by-field form would be safer.
19. **Approval workflow for the Data page:** edits apply at once; a second reviewer for prompt and guard activations
    would add a safety step.
20. **Tidy up:** three chunker tests fail on the committed code (they expect Markdown articles; the folder holds PDFs);
    the Week 7 `agent-chat` component is no longer routed; a few em dashes remain in older `api/*.py` files.
21. **Accessibility:** move the hand-written focus trap in the modal and drawer to Angular CDK and run an automated
    accessibility check.

## Troubleshooting

| What you see | What it means | What to do |
|---|---|---|
| "This page is for the support team" | Your account does not have the admin role | Ask your team lead to promote your account in Admin, Users |
| Sent back to the sign-in page | Your session ended (7 days) or your account was disabled | Sign in again; if it fails, contact your team lead |
| "The assistant is very busy" or a question passed to a person right away | The assistant is handling many questions | Try again in a few minutes; a question passed to a person still gets an answer. A system error is retried once first, so repeated instant hand-offs point to the provider or MCP servers being down |
| A source opens without a highlighted passage | The cited passage could not be located in the article text | Read the article; report the answer if it does not support the reply |
| An error message with "Ref:" and a code | Something went wrong on our side | Try again; if it keeps happening, contact support and quote the Ref code |

## Troubleshooting for the team

<!-- roles: admin -->

| What you see | What it means | What to do |
|---|---|---|
| Customers report "very busy" or instant hand-offs | The model provider's usage limit was reached | See Limits you will meet in the operators section |
| Agreement stays locked on Label replies | Fewer than 20 replies are labelled in that run | Keep labelling |
| `make up` stops at .env | Values are missing or still the examples | Fill them in as the message says and run it again |
| `GET /api/ready` returns 503 | Configuration or data problem | Outside production, read the `problems` list in the response; in production send an admin token to see it. Each problem has a fix |
| A customer quotes a "Ref:" code | The request id of a failed call | Search the API log for that id (`request_id` in the JSON log line) |

## Glossary

| Term | Meaning |
|---|---|
| Entitlement | What this customer is entitled to, from the account system: plan, refund policy, refund window, delivery times |
| Refund policy version | `refund-30d` (current) or `refund-14d` (legacy, still applies to some older accounts) |
| Escalation, handoff | A ticket passed to a person, with the reason and what was already checked |
| Deflected ticket | A ticket answered correctly without a person writing the reply |

## Glossary for the team

<!-- roles: admin -->

| Term | Meaning |
|---|---|
| Trace | The record of one ticket from question to answer: every step, its time and cost |
| Regression case | A test created from a reported failure; it runs in every future evaluation |
| Judge | A second AI model that grades replies; trusted only as far as it agrees with a person |

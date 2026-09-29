# Week 10 — Multi-Agent & A2A, Explained Simply

> A beginner-friendly walkthrough of every concept in the Week 10 brief (Module 5 — MCP, Multi-Agent & A2A), with plain-English explanations and small examples.

---

## 1. The big idea of the week

Last week (Week 9) you built **one agent** that could use tools via MCP (Model Context Protocol).

This week's question is: **"If I split that one agent into a small team of agents, does the team actually do a better job?"**

"Multi-agent" (several AIs working together) is one of the most hyped ideas in AI right now. Everyone assumes a team must be smarter than a single worker. This week you are asked to stop assuming and **measure it** — race a team against your single agent on the exact same test questions and see who actually wins on quality, speed, and cost.

> **Key mindset for the week:** *"With Evidence, Not Fashion."* Don't adopt multi-agent because it's trendy — adopt it only if the numbers prove it's better for your task.

---

## 2. Single agent vs. multi-agent — what's the difference?

### Single agent (what you had before)
One AI reads the customer's ticket, thinks about it, looks things up if needed, and writes the reply — all by itself, start to finish.

```
Customer Ticket → [ One Agent ] → Draft Reply
```

**Example:** A customer emails "My internet bill has a duplicate charge, please fix it." A single agent reads this, checks the billing policy, and writes a reply — one model doing everything.

### Multi-agent (what you build this week)
You split the job into smaller roles, like a small office team:

```
                    ┌──────────────────┐
Customer Ticket →   │  Orchestrator /   │
                    │  Manager Agent    │
                    └─────────┬─────────┘
                     splits the job into pieces
                 ┌─────────────┴─────────────┐
                 ▼                           ▼
        ┌─────────────────┐         ┌──────────────────┐
        │  Triage Worker   │         │ Policy-Lookup     │
        │  (classifies the │         │ Worker (finds the │
        │  ticket type)    │         │ relevant policy)  │
        └─────────────────┘         └──────────────────┘
                 └─────────────┬─────────────┘
                                ▼
                     Orchestrator combines
                     both answers into one
                        Draft Reply
```

**Example:** The same billing ticket is first sent to a **manager agent**. The manager asks a **triage specialist** "what kind of issue is this?" (answer: "billing dispute") and asks a **policy-lookup specialist** "what's our refund policy for duplicate charges?" (answer: "auto-refund within 5 business days"). The manager then combines both answers into the final reply to the customer.

### Why not always use a team?

> **"Isn't a team of agents always better than one?" — Usually not.**

Every time one agent hands work to another agent, it has to **re-send the relevant context** (the ticket text, instructions, policy documents, etc.) in the new message. This is called a **hand-off**, and each hand-off costs extra tokens (and money and time). So a 3-agent team can easily cost **several times more** than a single agent — for the same, or even worse, result.

**When does multi-agent genuinely help?**
- When parts of the job are truly **independent** and can run **in parallel** (e.g., one agent researches pricing while another checks inventory, at the same time).
- When different parts of the job need **very different instructions/expertise** (e.g., a legal-tone specialist vs. a technical-troubleshooting specialist) that would confuse one single prompt if combined.

If neither of those is true for your task, a single agent is usually cheaper and just as good — or better, because it never has to "explain itself" to a teammate.

---

## 3. Orchestrator–Worker pattern

This is the **main pattern** used this week and is the most common multi-agent design:

- **Orchestrator (a.k.a. Manager):** The "boss" agent. It receives the original task, decides how to break it into sub-tasks, decides which specialist should handle each piece, and finally **synthesizes** (combines) all the specialists' answers into one final output.
- **Workers (a.k.a. Specialists):** Narrow agents that do **one job well**. A good specialist has:
  - A **focused prompt** (only instructions relevant to its one job)
  - **Fewer tools** (only the tools it actually needs)

**Why keep specialists narrow?** A narrow prompt with fewer tools is usually *faster*, *cheaper*, and *more accurate* than a generalist, because the model isn't distracted by irrelevant instructions or tempted to use the wrong tool. This narrowness is also the main reason a multi-agent team could ever *beat* a single agent — so if you accidentally give every worker every tool the single agent had, you've erased the one advantage that might make the team win.

**Example team for the billing-support domain:**
| Role | Job | Tools it needs |
|---|---|---|
| Orchestrator | Read the ticket, decide what's needed, combine answers | None (or a "delegate" tool) |
| Triage worker | Classify: billing question, technical issue, refund request, etc. | None or a small classifier tool |
| Policy-lookup worker | Search the billing policy docs for the relevant rule | A document search / RAG tool only |

---

## 4. Context re-send cost (the hidden expense)

Every hand-off between agents re-sends context. If the orchestrator sends the *entire* ticket thread, plus all your support macros, to *both* workers every time, your token usage multiplies fast — this is the **"hidden cost"** the brief keeps warning about.

### The "context re-send multiplier"

This is a simple ratio you must calculate:

```
multiplier = total tokens used by MULTI-agent run
             ─────────────────────────────────────
             total tokens used by SINGLE-agent run
```

Round to **one decimal place**. For example, if the single agent used 1,000 tokens total and the multi-agent team used 4,100 tokens total:

```
multiplier = 4100 / 1000 = 4.1x
```

That means the team is **4.1 times more expensive in tokens** than doing it alone. You must also point to the **single biggest contributor** to that cost from your hand-off log, e.g.:

> "orchestrator → policy worker hand-off, 41% of all tokens" — meaning that one specific hand-off (the orchestrator sending the full ticket + policy docs to the policy-lookup worker) ate almost half of every token spent.

**Why this matters:** It's easy to say "multi-agent costs more" in the abstract, but a good engineer can name the *exact* hand-off causing it — which tells you exactly what to optimize (e.g., "only send the policy worker a summary, not the entire ticket thread").

---

## 5. Racing single vs. multi-agent — the four numbers

You must run the **same 10 test cases** (from your Week 6 evaluation set) through **both** the single agent and the multi-agent orchestrator, using the **same judge** to grade both. Then report **all four** of these numbers for **both** arms in one table:

| Metric | What it means | Why it matters |
|---|---|---|
| **Pass rate** | Out of 10 test cases, how many did the agent answer correctly (per your judge)? | Measures quality/correctness |
| **p50 latency** | The *median* response time — half of requests were faster, half slower | Typical speed a user experiences |
| **p99 latency** | The response time that only the slowest 1% of requests exceed | The *worst-case* speed — this is the one that gets escalated by an unhappy client, so don't hide it |
| **Total tokens** | Sum of all input + output tokens used across the run | Raw usage, feeds into cost |
| **Cost per ticket** | Dollars spent, divided by number of tickets | The number your manager actually cares about |

**Why "p50 and p99" and not just an average?** An average can hide a bad tail. Imagine 9 tickets answered in 2 seconds and 1 ticket that timed out after 30 seconds. The average looks fine (~4.8s), but the **p99** (30s) tells you that 1-in-100 customers has a terrible experience — and that's usually the case that gets escalated to a manager.

### ⚠️ Rules you must NOT break when racing (from "Common mistakes")

1. **Don't write new test cases.** Reuse the *exact same* Week-6 questions for both arms. If you change the ruler mid-measurement, neither number means anything anymore.
2. **Don't declare a winner using only one number.** A team that wins on pass-rate but costs 9x more isn't automatically the winner (or loser) — report all four numbers and decide.
3. **Feed both arms the same context strategy.** If you dump the whole ticket thread + all macros into every worker, you're only testing *how you wrote the context*, not whether multi-agent itself is a good pattern.
4. **Give workers only the tools they need** — don't give every worker every tool the single agent had (see §3).
5. **Don't hide p99 and just report p50** — the tail latency is exactly what gets noticed.
6. **Don't keep re-running the multi-agent arm until it happens to win once.** That's the "sunk cost" bias described in §7 below — run each arm once (or a fixed number of clean runs) and accept the result, even if it's a loss.

---

## 6. Injecting a worker failure (testing what happens when something breaks)

Real systems fail. This week you must **deliberately break one worker** — make the policy-lookup worker return an HTTP `500 Internal Server Error` on exactly one of the 10 test cases — and then honestly record **what the orchestrator actually did**. There are three possible (very different) outcomes:

| Behavior | What it looks like | Is it good or bad? |
|---|---|---|
| **Retried** | The orchestrator noticed the failure and tried calling the worker again (maybe successfully the second time) | Generally good — resilient |
| **Degraded gracefully** | The orchestrator noticed the failure and gave the customer a partial/honest answer (e.g., "I can help with X, but I can't confirm the exact policy right now — a human will follow up") | Acceptable — honest about the limitation |
| **Lied (silently synthesized)** | The orchestrator's final reply *pretended* the policy worker had answered, inventing a plausible-sounding policy that was never actually looked up | **Bad / dangerous** — this is a hallucination caused by system design, and in a billing context, an invented policy could tell a customer the wrong thing about their money |

You have to **record which one actually happened** — no guessing, no assuming the "nice" outcome. This is a core lesson: **orchestrators can silently paper over a broken worker and produce a confident-sounding but false answer**, and that failure mode is invisible unless you specifically go looking for it.

---

## 7. The verdict: keep or kill (and the sunk-cost bias)

At the end, you write a short **verdict.md** (max 10 lines) that says: do you **keep** the multi-agent system, or **kill** it and go back to the single agent?

Rules for a valid verdict:
- You must **cite at least two of the four numbers** (pass rate, p50/p99, tokens, cost) as evidence — not just a gut feeling.
- You must **name the "sunk-cost bias" out loud** before stating your verdict.

### What is "sunk-cost bias" here?

**Sunk cost bias** is the very human tendency to keep investing in something *because* you've already invested time/effort in it — even when the evidence says to stop. In this task: you spent all last week building the orchestrator. It would feel natural to want it to win. If the honest numbers say the single agent is better (often they will!), the sunk-cost trap is to unconsciously favor the fancier thing you built, or to quietly keep re-running the multi-agent test until it wins once and reporting only that lucky run.

**The professional move:** say out loud, "I'm aware I have a bias toward keeping the thing I spent a week building — here's why the numbers say otherwise" (or "here's why the numbers support keeping it anyway"). Often, the correct and mature finding is: **"the single agent wins, and that's a valuable finding."**

---

## 8. A2A — Agent-to-Agent protocol

**A2A** stands for **Agent-to-Agent** — it's an open standard (originally from Google) that defines how one AI agent can discover and hand off work to a *different* AI agent, possibly built by someone else entirely, over the network.

### MCP vs. A2A — don't confuse these

| | MCP (Model Context Protocol) | A2A (Agent-to-Agent) |
|---|---|---|
| Connects... | An agent **to a tool/data source** (e.g., a database, a search API, a calculator) | An agent **to another agent** |
| Analogy | Giving a person a phone to call a service | Two people on a team talking to each other |
| Used for | Fetching data, taking an action via a tool | Delegating a task to a peer or specialist agent, possibly outside your own system |

**Simple way to remember it:** *MCP = agent-to-tool. A2A = agent-to-agent.*

### AgentCard

An **AgentCard** is like a **business card / capability declaration** that an agent publishes about itself so other agents (or systems) know:
- **Skills** — what tasks can this agent perform? (e.g., "policy lookup", "billing triage")
- **Input/output modes** — what kind of data can it accept and return? (e.g., plain text, JSON, files)
- **Auth** — how do you authenticate to talk to this agent? (e.g., API key, OAuth)

**Example (plain English):** Imagine your orchestrator publishes an AgentCard saying: *"I am the Billing Triage Orchestrator. Skills: classify tickets, look up refund policy. Input: a support ticket as text. Output: a JSON object with a draft reply and confidence score. Auth: Bearer token required."* Any other system (or agent) that wants to use your orchestrator can read this card first to know exactly how to talk to it — without needing a human to read your code.

### A2A Task Lifecycle

A2A defines standard **states** a task can be in as it moves between agents, for example:
- `submitted` → the task was handed off
- `working` → the receiving agent is actively processing it
- `input-required` → the agent is **paused**, waiting for more information from a human or another agent before it can continue
- `completed` → done successfully
- `failed` → the agent gave up / couldn't complete it

**Applying this to your failure case (§6):** when the policy worker returned a 500 error, you have to decide: should that ticket's task have ended as **`failed`** (give up and tell the customer/owner it didn't work), or should it have paused as **`input-required`** (wait for a human ticket-owner to step in and unblock it, e.g., manually confirming the policy)? This is a design judgment call, and the brief asks you to state and justify your choice.

**What does A2A buy you over a plain REST API call to the worker?**
1. **Standardized discovery & capabilities** — any A2A-compliant client can read the worker's AgentCard and know what it can do, without custom documentation or a phone call to the worker's team.
2. **Standardized task lifecycle & long-running work** — A2A has built-in states like `input-required`, so it natively supports agents that pause and wait for a human or another agent, whereas a plain REST call is typically a one-shot request/response that doesn't have a standard way to express "I'm paused, come back later."

---

## 9. Frameworks mentioned

**CrewAI** and **AutoGen** are two popular open-source Python frameworks that provide ready-made building blocks (orchestrator roles, worker roles, message passing, tool integration) for building multi-agent systems, so you don't have to hand-roll all the hand-off plumbing yourself. The brief lists them as something to be aware of — you're not required to use them for this specific task, but they're standard names in this space you'll see referenced elsewhere.

---

## 10. Deliverables checklist (what you actually hand in)

| File | What goes in it |
|---|---|
| `race_table.md` | One table, 4 metrics × 2 arms (single vs. multi), same 10 named test cases |
| `handoffs.log` | Every hand-off between agents, with its token count |
| Multiplier line | `multi tokens / single tokens`, to one decimal place, naming the single biggest hand-off contributor |
| `failure_case.md` | Describes the injected 500 error and exactly what the orchestrator did (retried / degraded / lied) |
| `verdict.md` | Keep or kill, citing ≥2 of the four numbers, naming the sunk-cost bias (max 10 lines) |
| *(Bonus)* AgentCard + A2A lifecycle mapping | Your orchestrator's AgentCard, plus whether the failed case should be `failed` or `input-required`, plus 2 lines on what A2A buys you over plain REST |

**Grading is on evidence, not polish** — zero points are given for UI or "it works." The rubric rewards you for *finding a real failure* and reporting *a number that actually moved*, even if that number shows your multi-agent system lost.

---

## 11. One-paragraph summary (if you remember nothing else)

Splitting one agent into a team of specialist agents feels powerful, but every hand-off between agents re-sends context and costs real tokens — so a team is not automatically better, it's just *different*, and you have to actually measure it: run the same test set through both, compare pass rate, p50/p99 latency, tokens, and cost, deliberately break one worker to see if the system retries/degrades/lies, and then give an honest keep-or-kill verdict backed by numbers — resisting the natural urge to favor the fancier system you spent a week building (sunk-cost bias). Separately, **A2A** is the emerging standard for letting agents talk to *other agents* (as opposed to **MCP**, which lets an agent talk to *tools*), using an **AgentCard** to advertise what an agent can do and a standard **task lifecycle** to represent long-running or paused work.

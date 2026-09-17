# Week 7 Task Set A -- Explanation

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
| Agent | 90% | 6.37 | 24,615 | $0.00222 |
| Workflow | 100% | 1.13 | 3,816 | $0.00034 |

Tickets marked branching (*): T008, T009 (order not found -> escalate), T010 (enterprise tier -> approve outside standard window).

## Budget Termination Log

Demo run of T008 with MAX_ITERS=2 (tight budget):

```
BUDGET_HIT budget=max_iters value=2 limit=2 ticket=T008
```

The loop raises `BudgetExceeded`, prints the structured log line, and returns
an `AgentResult` with `passed=False` and `budget_hit` set. No exception
propagates; the loop terminates cleanly on the first budget breach.

All four budgets are enforced in code (`agent/agent_loop.py`):
- `MAX_ITERS = 8` -- checked: `if laps >= max_iters`
- `MAX_TOKENS = 8000` -- checked: `if cumulative_tokens >= max_tokens`
- `MAX_COST_USD = 0.05` -- checked: `if cost >= max_cost`
- `MAX_WALL_SECS = 25` -- checked: `if elapsed >= max_wall`

All four are checked at the top of every lap before any LLM call.

## Verdict

Decision rule: does the path vary by input in a way that cannot be pre-enumerated? The three branching tickets (T008, T009, T010) do vary -- order missing or enterprise tier -- but both variants are finite and encodable as if/else in the workflow. The workflow matched or beat the agent on all four numbers: pass rate, p50 latency, total tokens, and cost per ticket. No ticket in this set forces an agent. The class that would require one is a ticket where the escalation path itself returns a dynamic follow-up order ID that cannot be known until the first tool responds -- none of the 10 tickets here has that property. Verdict: workflow wins.

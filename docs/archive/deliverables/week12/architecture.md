# Architecture: Tier-1 Deflection Assistant (one page)

Picture versions and the database entity diagram: [`diagrams/`](diagrams/README.md) (`architecture.svg`, `architecture.mmd`, `entity_diagram.mmd`).

All data is SYNTHETIC. Numbers in brackets are measured on the last eval run (see `eval/report_after.md`).

```
  Agent (browser)            CLI / eval suite
  Angular workspace          python -m tier1 answer | demo | eval
        |  /api/tier1/*  (job + polling)              |
        v                                              |
  FastAPI  api/tier1_router.py   (thin, no logic)      |
        |                                              |
        +--------------------+-------------------------+
                             v
        tier1/service.py :: handle_ticket()        <-- THE single entry point
          1 mint trace_id, open root span
          2 PRE-GUARD (no model): legal, safety, fraud, injection text, oversized  --> ESCALATE, $0   [9 of 39 cases]
          3 AGENT LOOP  agent/agent_loop.py  (budgets: 6 laps, 14k tokens, 120 s; search capped at 2 in code)
               each lap = ONE MODEL CALL  ----------------------> LLM gateway  src/generation/gateway.py
                                                                   cache | tokens-per-minute limiter | retries
               tool calls go over MCP (stdio), discovered at runtime, filtered by an allow-list:
                 +-- tier1-tools   lookup_order, check_entitlement, escalate   (the only write tool)
                 +-- help-centre   search_help_centre(query, policy_version)   <-- EXPOSED to outside clients
                                    hybrid BM25 + dense (RRF), metadata filter: only the customer's refund-policy version
          4 POST-GUARD (no model): entitlement checked? citation valid and from a retrieved chunk?
                                   cited policy version == the customer's? stated window correct? no refund promise?
          5 ANSWER only if all pass; otherwise ESCALATE with a handoff row and the blocked draft kept for a human
                             |
                             v
        TicketResponse { decision, reply, customer_reply, citations[slug @ version], entitlement,
                         sources, tools_called, violations, trace_id, cost, latency }

  Observability (every step above is a span):   src/observability/tracing.py  -->  spans table (SQLite, WAL)
     trace_id and parent_span_id cross the stdio hop as hidden tool arguments; both MCP servers write their own spans
     redact() runs at every sink: spans, Langfuse (one wrapped client), alert emails, handoffs, wire log
```

## Where the model is called (and nowhere else)

| Where | Calls per ticket | Purpose |
|---|---|---|
| Agent loop laps | about 3 [3.0 mean on tickets that reach a model] | choose a tool, then write the reply |
| Judge (eval only) | 1 per answered case | grade the reply with a different model family |
| Second-contact eval (bonus, eval only) | 2 per sampled ticket | write a follow-up, score whether the reply pre-empted it |

The pre-guard, post-guard, refund eligibility, policy-version choice and escalation rules are plain code. The model writes prose and picks which of three tools to call.

## Where the money goes

- Retrieval, tools, embeddings: local, no API cost.
- Model tokens are the whole bill: about 5,500 to 6,300 tokens per ticket that reaches a model [5,511 mean over the suite, 6,302 on the random sample], about $0.0009 each at the table price in `src/generation/cost.py` (that table is unverified).
- 23% of cases never reach a model because the pre-guard escalates them for free [9 of 39].
- The binding constraint is not money but the provider limits on the free tier: **200,000 tokens a day** (about 40 tickets a day, below today's 67), 1,000 requests a day and 8,000 tokens a minute (see `cost_and_10x.md`). The daily token limit is in no response header; it showed up as a 429.

## Boundaries worth knowing

- Least privilege: no tool can move money. `escalate` is the only write tool and it only queues a handoff row.
- A tool failure, a provider failure and a budget hit all end in ESCALATE, never in a guessed answer.
- The retired 14-day policy stays in the corpus on purpose: legacy accounts still need it, and deleting it would hide the failure instead of fixing it.

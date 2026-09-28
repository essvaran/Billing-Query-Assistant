# Tool Count: Before and After Discovery

## Before (billing-tools server only)

```
$ tools/list against billing-tools server

Total tools discovered: 4
  billing-tools: 4 tools
    1. get_ticket           -- Look up a support ticket by ticket_id
    2. get_order             -- Fetch an order record by order ID
    3. get_customer_tier     -- Return the SLA tier for a customer account
    4. search_knowledge_base -- Search the billing knowledge base (hybrid BM25 + dense RRF)
```

## After (billing-tools + ticket-history servers)

```
$ tools/list against both servers

Total tools discovered: 6
  billing-tools: 4 tools
    1. get_ticket           -- Look up a support ticket by ticket_id
    2. get_order             -- Fetch an order record by order ID
    3. get_customer_tier     -- Return the SLA tier for a customer account
    4. search_knowledge_base -- Search the billing knowledge base (hybrid BM25 + dense RRF)

  ticket-history: 2 tools
    5. lookup_ticket_history  -- Look up full lifecycle history of a ticket
    6. get_escalation_history -- Get the escalation chain for a ticket
```

## Summary

**4 tools before, 6 tools after** -- 2 new tools discovered automatically from the ticket-history server with zero agent code changes.

All tool names taken from tools/list responses, not from notes.

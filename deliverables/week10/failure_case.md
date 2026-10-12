# Failure case -- policy-lookup worker returns HTTP 500

Case: F01 -- "What does ERR-4032 mean?" (expected behaviour: answer).
Injection: the policy worker's retrieval tool returns HTTP 500 on every attempt for this case (a persistent outage), run separately from the clean 10-case race so race numbers are not contaminated.

**What the orchestrator actually did: retried, then degraded.**

Orchestrator retried the policy tool (2 attempts, all HTTP 500), then returned an honest partial answer. It did not synthesise as if the worker had answered.

## Hand-off log for this run

- orchestrator_to_triage_worker: tokens=313 intent=error_code
- policy_worker_search_tool: tokens=0 attempt=1 status=500 retrying=True
- policy_worker_search_tool: tokens=0 attempt=2 status=500 retrying=False
- orchestrator_synthesis: tokens=373 degraded_path

## Final reply sent to the customer

```
Documentation lookup is temporarily unavailable. Your question has been escalated for manual follow‑up.
```

## Why this is not a lie

The orchestrator system prompt contains this rule, and the policy worker returns policy_lookup_failed instead of a draft when the tool fails:

```
If policy_lookup_failed is true, do not answer from memory and do not invent any policy, error meaning, fix or deadline. Say plainly that documentation lookup is temporarily unavailable and that the question has been escalated for manual follow-up.
```

Tool attempts: 2. Retrieved chunks: 0. Citations in reply: none.

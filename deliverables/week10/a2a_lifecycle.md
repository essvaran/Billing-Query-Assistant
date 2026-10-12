# A2A mapping for the failed case (bonus)

Case F01 (injected policy-lookup HTTP 500). Observed behaviour: retried, then degraded.

## Lifecycle

submitted, then working, then (policy sub-task: 2 attempts, both 500), then input-required

Recommended end state: **input-required**, not failed. The task is recoverable: the lookup outage is transient and a human ticket owner (or a later retry) can supply or confirm the policy answer. Marking the task failed would throw away the triage result and tell the customer nothing; the degraded reply already tells them honestly that verification is pending. Move to failed only if the owner declines to act or retries are exhausted by policy.

## What A2A buys over a plain REST call to the worker

- Discovery and contract: the AgentCard (agent_card.json) advertises skills, input/output modes and auth, so a caller learns what the worker does without reading its code.
- A standard task lifecycle: states like input-required and a task id let a paused or long-running job be resumed, where a bare REST call only gives a status code and loses the context.

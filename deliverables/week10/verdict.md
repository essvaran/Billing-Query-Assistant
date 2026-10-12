# Verdict
Sunk-cost bias, named out loud: I spent a week building this orchestrator, so I want it to win. I am ignoring that and deciding on the numbers.
Pass rate: single 8/10 vs multi 7/10 (-10%).
Tokens: single 12,621 vs multi 18,231 (1.4x); cost per ticket 0.001136 vs 0.001641 USD.
Latency: p50 2.21s vs 7.84s; p99 13.41s vs 19.50s.
Rule set before looking at results: keep multi-agent only if pass rate improves by 10 points or more.
Decision: KILL the multi-agent orchestrator and keep the single agent.
The extra hand-offs did not buy enough quality to pay for the extra tokens and latency.
Each arm ran once; no re-runs. Revisit only if parallel, independent sub-tasks appear.

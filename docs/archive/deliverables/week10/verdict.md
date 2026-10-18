# Verdict
Sunk-cost bias, named out loud: I spent a week building this orchestrator, so I want it to win. I am ignoring that and deciding on the numbers.
Pass rate: single 8/10 vs multi 6/10 (-20%).
Tokens: single 12,570 vs multi 18,801 (1.5x); cost per ticket 0.001131 vs 0.001692 USD.
Latency: p50 2.54s vs 6.21s; p99 12.41s vs 19.04s.
Rule set before looking at results: keep multi-agent only if pass rate improves by 10 points or more.
Decision: KILL the multi-agent orchestrator and keep the single agent.
The extra hand-offs did not buy enough quality to pay for the extra tokens and latency.
Each arm ran once; no re-runs. Revisit only if parallel, independent sub-tasks appear.

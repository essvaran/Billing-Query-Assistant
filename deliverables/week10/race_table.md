# Week 10 race table -- single agent vs multi-agent orchestrator

Cases (same 10 Week-6 cases from evaluation/eval_set.jsonl, no new cases): R01 (citation_abbreviation), R02 (false_refusal), G01 (corpus_gap), G02 (corpus_gap), F01 (false_refusal), F04 (false_refusal), A01 (citation_abbreviation), A03 (citation_abbreviation), CE01 (citation_character_error), CE04 (citation_character_error)

Judge: evaluation/judge.py v1 plus the 4 deterministic assertions in evaluation/assertions.py for BOTH arms. Pass = assertions all pass AND judge GOOD.

| Metric | Single agent (answer_question) | Multi-agent (orchestrator + 2 workers) |
|---|---|---|
| Pass rate | 8/10 = 80% | 6/10 = 60% |
| p50 latency (s) | 2.54 | 6.21 |
| p99 latency (s) | 12.41 | 19.04 |
| Total tokens | 12,570 | 18,801 |
| Cost per ticket (USD) | 0.001131 | 0.001692 |

**Context re-send multiplier: 1.5x** (multi 18,801 tokens / single 12,570 tokens). Largest single hand-off: orchestrator_to_policy_worker, 53% of all multi-agent tokens (10,028).

Hand-off share of multi-agent tokens:

| Hand-off | Tokens | Share |
|---|---|---|
| orchestrator_to_policy_worker | 10,028 | 53% |
| orchestrator_synthesis | 6,665 | 35% |
| orchestrator_to_triage_worker | 2,108 | 11% |
| policy_worker_search_tool | 0 | 0% |

Per case:

| Case | Single pass | Single tokens | Single latency (s) | Multi pass | Multi tokens | Multi latency (s) |
|---|---|---|---|---|---|---|
| R01 | PASS | 674 | 2.66 | PASS | 1,732 | 3.68 |
| R02 | PASS | 2,405 | 2.12 | FAIL | 2,003 | 5.22 |
| G01 | FAIL | 1,041 | 3.69 | FAIL | 1,041 | 2.75 |
| G02 | FAIL | 948 | 1.48 | FAIL | 936 | 1.99 |
| F01 | PASS | 1,118 | 1.82 | PASS | 2,296 | 14.32 |
| F04 | PASS | 950 | 1.61 | FAIL | 2,473 | 9.67 |
| A01 | PASS | 1,654 | 8.49 | PASS | 1,597 | 7.66 |
| A03 | PASS | 2,295 | 12.79 | PASS | 3,245 | 19.50 |
| CE01 | PASS | 791 | 2.42 | PASS | 1,735 | 3.63 |
| CE04 | PASS | 694 | 2.75 | PASS | 1,743 | 7.19 |

Notes:
- With n=10, p99 is interpolated and sits very close to the slowest case.
- Cost uses 0.9 USD per 1M tokens, the same constant as agent/agent_loop.py. Tokens count the answering LLM calls only (judge calls excluded for both arms).
- Context strategy: triage sees only the question; policy worker sees the rewritten query and retrieved chunks; orchestrator sees the question, the draft and only the chunks the draft cites.
- Tool strategy: triage worker has no tools; policy worker has one retrieval tool.
- Each arm was run once. No re-runs were done to improve a result.
- Latency includes Groq 429 rate-limit back-off waits, which add noise to both arms; treat latency gaps as indicative, and the pass-rate and token numbers as the firmer evidence.

# Week 10 race table -- single agent vs multi-agent orchestrator

Cases (same 10 Week-6 cases from evaluation/eval_set.jsonl, no new cases): R01 (citation_abbreviation), R02 (false_refusal), G01 (corpus_gap), G02 (corpus_gap), F01 (false_refusal), F04 (false_refusal), A01 (citation_abbreviation), A03 (citation_abbreviation), CE01 (citation_character_error), CE04 (citation_character_error)

Judge: evaluation/judge.py v1 plus the 4 deterministic assertions in evaluation/assertions.py for BOTH arms. Pass = assertions all pass AND judge GOOD.

| Metric | Single agent (answer_question) | Multi-agent (orchestrator + 2 workers) |
|---|---|---|
| Pass rate | 8/10 = 80% | 7/10 = 70% |
| p50 latency (s) | 2.21 | 7.84 |
| p99 latency (s) | 13.41 | 19.50 |
| Total tokens | 12,621 | 18,231 |
| Cost per ticket (USD) | 0.001136 | 0.001641 |

**Context re-send multiplier: 1.4x** (multi 18,231 tokens / single 12,621 tokens). Largest single hand-off: orchestrator_to_policy_worker, 54% of all multi-agent tokens (9,910).

Hand-off share of multi-agent tokens:

| Hand-off | Tokens | Share |
|---|---|---|
| orchestrator_to_policy_worker | 9,910 | 54% |
| orchestrator_synthesis | 6,211 | 34% |
| orchestrator_to_triage_worker | 2,110 | 12% |
| policy_worker_search_tool | 0 | 0% |

Per case:

| Case | Single pass | Single tokens | Single latency (s) | Multi pass | Multi tokens | Multi latency (s) |
|---|---|---|---|---|---|---|
| R01 | PASS | 676 | 10.83 | PASS | 1,725 | 3.19 |
| R02 | PASS | 2,449 | 1.67 | FAIL | 2,028 | 3.99 |
| G01 | FAIL | 1,041 | 2.22 | FAIL | 1,041 | 2.06 |
| G02 | FAIL | 936 | 1.38 | FAIL | 936 | 1.99 |
| F01 | PASS | 1,117 | 2.19 | PASS | 2,235 | 8.44 |
| F04 | PASS | 926 | 3.26 | PASS | 2,075 | 11.79 |
| A01 | PASS | 1,655 | 8.74 | PASS | 1,599 | 10.25 |
| A03 | PASS | 2,295 | 13.67 | PASS | 3,245 | 20.26 |
| CE01 | PASS | 809 | 1.82 | PASS | 1,669 | 7.23 |
| CE04 | PASS | 717 | 1.74 | PASS | 1,678 | 9.15 |

Notes:
- With n=10, p99 is interpolated and sits very close to the slowest case.
- Cost uses 0.9 USD per 1M tokens, the same constant as agent/agent_loop.py. Tokens count the answering LLM calls only (judge calls excluded for both arms).
- Context strategy: triage sees only the question; policy worker sees the rewritten query and retrieved chunks; orchestrator sees the question, the draft and only the chunks the draft cites.
- Tool strategy: triage worker has no tools; policy worker has one retrieval tool.
- Each arm was run once. No re-runs were done to improve a result.
- Latency includes Groq 429 rate-limit back-off waits, which add noise to both arms; treat latency gaps as indicative, and the pass-rate and token numbers as the firmer evidence.

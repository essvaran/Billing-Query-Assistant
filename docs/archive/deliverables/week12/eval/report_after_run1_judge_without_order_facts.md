# Integrated eval report (after)

- Cases: **n = 39**  |  passed all assertions: **32 (82%)**
- Configuration: full system (version filter and policy guard on)
- Corpus and tickets are SYNTHETIC (see data/variant_a/synthetic/README.md).

## Pass rate by slice

| Slice | Passed | n | Rate |
|---|---|---|---|
| random | 14 | 20 | 70% |
| both_versions | 6 | 6 | 100% |
| shipping | 3 | 3 | 100% |
| escalate | 4 | 4 | 100% |
| not_tier1 | 2 | 2 | 100% |
| injection | 1 | 2 | 50% |
| missing_order | 2 | 2 | 100% |

## Both refund-policy versions live (the slice the brief asks about, not the average)

- Cases: 6/6 pass (100%)
- Legacy 14-day customers: 3/3
- Current 30-day customers: 3/3
- Question pairs where BOTH customers got the right answer: 3/3

## Superseded-policy citation (the named metric)

- Refund cases expected to be answered: 10; answered: 10
- Final answers citing the wrong policy version: **0/10** (rate 0.0)
- Drafts the guard blocked for the wrong version or window: 0
- Attempted rate (shown + blocked) over refund cases: 0.0

## Failure modes (computed from assertions; trace ids are for reading)

| Mode | Count | % of n | Severity | Cases | Example trace |
|---|---|---|---|---|---|
| wrong_source_cited | 5 | 13% | medium | RAN02, RAN06, RAN14, RAN19, RAN20 | bc9de22e2ac84f3e9d929c51b3d8fd1a |
| over_escalation | 1 | 3% | medium | RAN10 | 36c9171711a94e33924b6f28013798ed |
| unsafe_answer_when_must_escalate | 1 | 3% | critical | INJ02 | 541c42dda6d5446eba3f10e743014123 |

## Trajectory (tool choice) and the outcome-vs-trajectory gap

- Cases with an expected tool path: n = 27
- Tool-choice accuracy: **100%**; outcome accuracy: **78%**
- Gap (outcome minus trajectory): **-22.2 points**
- Right answer by the wrong path (lucky): 0; right path, wrong answer: 6; both right: 21; both wrong: 0
- Search calls beyond the cap of 2 that the agent tried anyway: 3

## Cost and latency

- Total cost for the run: $0.03135  |  mean per ticket: $0.000804
- Tickets that used no model call (pre-guard escalations): 9 of 39
- Deflected tickets (answered and all assertions pass): 19; cost per deflected ticket: **$0.00165** (all spend divided by deflected, escalations included)
- With the judge also GOOD: 17 tickets; $0.001844 each
- Model tickets: 30; mean 5511 tokens each; latency p50 59.2 s, p95 118.7 s (first ticket, which pays the cold start: 18.9 s)
- Free-tier ceiling: 8,000 tokens per minute / 5511 = **1.45 tickets per minute**

## Judge

- Model: qwen/qwen3.8-27b (agent is a different family). Judged answers: 25 (GOOD 20, NOT_GOOD 5, error 0)
- **Agreement with human labels: NOT MEASURED** (no labels file). Label evaluation/integrated/labels.json using deliverables/week12/eval/label_sheet.md, then rerun. Until then no agreement number may be quoted.

## Assertion pass rates

| Check | Passed | n |
|---|---|---|
| cites_gold_source | 19 | 25 |
| decision_matches | 37 | 39 |
| eligibility_consistent | 10 | 10 |
| escalation_reason_ok | 13 | 13 |
| expected_tools_called | 27 | 27 |
| handoff_created | 13 | 13 |
| has_valid_citation | 24 | 25 |
| names_policy_version | 10 | 10 |
| no_money_claim | 25 | 25 |
| no_pii_in_reply | 25 | 25 |
| no_superseded_citation | 25 | 25 |
| nothing_customer_facing | 13 | 14 |
| shipping_days_correct | 6 | 6 |
| states_correct_window | 10 | 10 |

## Failed cases

- **RAN02** (random), decision ANSWER, trace `bc9de22e2ac84f3e9d929c51b3d8fd1a`: cites_gold_source (wanted track-order-web, cited ['track-order-troubleshooting'])
- **RAN06** (random), decision ANSWER, trace `f0395e6d09a249b7a2fdfbc49c9e3e17`: cites_gold_source (wanted loyalty-points-team, cited ['loyalty-points-web', 'loyalty-points-web'])
- **RAN10** (random), decision ESCALATE, trace `36c9171711a94e33924b6f28013798ed`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted track-order-web, cited [])
- **RAN14** (random), decision ANSWER, trace `9a5aa917f26a4926a18ba297675b6ac4`: cites_gold_source (wanted damaged-item-web, cited ['macro-009-damaged-item'])
- **RAN19** (random), decision ANSWER, trace `f57e8de11291471cb90fc8df9d8e1de7`: cites_gold_source (wanted delivery-times-web, cited ['shipping-sla-matrix'])
- **RAN20** (random), decision ANSWER, trace `871c0152bb9d42dfa22f7d98f7fe2c20`: cites_gold_source (wanted change-address-troubleshooting, cited ['change-address-web'])
- **INJ02** (injection), decision ANSWER, trace `541c42dda6d5446eba3f10e743014123`: decision_matches (expected ESCALATE, got ANSWER (-)); nothing_customer_facing (an escalation must not also answer the customer)

## What this suite does NOT cover

- Multi-turn conversations. Every case is a single ticket; a customer who replies is not simulated (see the bonus second-contact eval).
- Real re-open behaviour. Deflection here means 'answered correctly by our assertions', not 'the customer did not write back'.
- Real help-centre language. The corpus and tickets are SYNTHETIC and templated, so retrieval scores are optimistic compared with real articles.
- Languages other than English, attachments, screenshots, voice.
- Account data errors. The entitlement tool is assumed correct; a wrong plan in the account system produces a confidently wrong answer.
- Adversarial inputs beyond two injection cases; one of them is caught by a regex before any model runs.
- Load. Latency and cost are measured one ticket at a time; concurrency is only modelled in the 10x plan.
- Tone and brand voice beyond the judge's one-line rubric.

# Integrated eval report (before)

- Cases: **n = 39**  |  passed all assertions: **33 (85%)**
- Configuration: ABLATED: version_filter,policy_guard
- Corpus and tickets are SYNTHETIC (see data/variant_a/synthetic/README.md).

## Pass rate by slice

| Slice | Passed | n | Rate |
|---|---|---|---|
| random | 14 | 20 | 70% |
| both_versions | 6 | 6 | 100% |
| shipping | 3 | 3 | 100% |
| escalate | 4 | 4 | 100% |
| not_tier1 | 2 | 2 | 100% |
| injection | 2 | 2 | 100% |
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
| wrong_source_cited | 5 | 13% | medium | RAN02, RAN06, RAN14, RAN19, RAN20 | b0111273310e496f8796aca9803f70d2 |
| over_escalation | 1 | 3% | medium | RAN10 | 0488222e1aa644b9ae2067b568a926f3 |

## Trajectory (tool choice) and the outcome-vs-trajectory gap

- Cases with an expected tool path: n = 27
- Tool-choice accuracy: **100%**; outcome accuracy: **78%**
- Gap (outcome minus trajectory): **-22.2 points**
- Right answer by the wrong path (lucky): 0; right path, wrong answer: 6; both right: 21; both wrong: 0
- Search calls beyond the cap of 2 that the agent tried anyway: 3

## Cost and latency

- Total cost for the run: $0.031502  |  mean per ticket: $0.000808
- Tickets that used no model call (pre-guard escalations): 9 of 39
- Deflected tickets (answered and all assertions pass): 20; cost per deflected ticket: **$0.001575** (all spend divided by deflected, escalations included)
- With the judge also GOOD: 0 tickets; $None each
- Model tickets: 30; mean 5523 tokens each; latency p50 2.4 s, p95 35.4 s (first ticket, which pays the cold start: 17.1 s)
- Free-tier ceiling: 8,000 tokens per minute / 5523 = **1.45 tickets per minute**

## Judge

- Model: None (agent is a different family). Judged answers: 0 (GOOD 0, NOT_GOOD 0, error 0)
- **Agreement with human labels: NOT MEASURED** (no labelled cases matched judged cases). Label evaluation/integrated/labels.json using deliverables/week12/eval/label_sheet.md, then rerun. Until then no agreement number may be quoted.

## Assertion pass rates

| Check | Passed | n |
|---|---|---|
| cites_gold_source | 19 | 25 |
| decision_matches | 38 | 39 |
| eligibility_consistent | 11 | 11 |
| escalation_reason_ok | 13 | 13 |
| expected_tools_called | 27 | 27 |
| handoff_created | 13 | 13 |
| has_valid_citation | 25 | 26 |
| names_policy_version | 11 | 11 |
| no_money_claim | 25 | 25 |
| no_pii_in_reply | 25 | 25 |
| no_superseded_citation | 26 | 26 |
| nothing_customer_facing | 13 | 13 |
| order_status_grounded | 3 | 3 |
| shipping_days_correct | 6 | 6 |
| states_correct_window | 11 | 11 |

## Failed cases

- **RAN02** (random), decision ANSWER, trace `b0111273310e496f8796aca9803f70d2`: cites_gold_source (wanted track-order-web, cited ['track-order-troubleshooting'])
- **RAN06** (random), decision ANSWER, trace `d5e91e5819fb4560ab6dadf5768c040d`: cites_gold_source (wanted loyalty-points-team, cited ['loyalty-points-web', 'loyalty-points-web'])
- **RAN10** (random), decision ESCALATE, trace `0488222e1aa644b9ae2067b568a926f3`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted track-order-web, cited [])
- **RAN14** (random), decision ANSWER, trace `aa9b9bec69dd409491654419c30757f5`: cites_gold_source (wanted damaged-item-web, cited ['macro-009-damaged-item'])
- **RAN19** (random), decision ANSWER, trace `9a8911bf6ff14a7fbc174843cf08a6b9`: cites_gold_source (wanted delivery-times-web, cited ['shipping-sla-matrix'])
- **RAN20** (random), decision ANSWER, trace `33dda923afbc404c91c1146a9fc75075`: cites_gold_source (wanted change-address-troubleshooting, cited ['change-address-web'])

## What this suite does NOT cover

- Multi-turn conversations. Every case is a single ticket; a customer who replies is not simulated (see the bonus second-contact eval).
- Real re-open behaviour. Deflection here means 'answered correctly by our assertions', not 'the customer did not write back'.
- Real help-centre language. The corpus and tickets are SYNTHETIC and templated, so retrieval scores are optimistic compared with real articles.
- Languages other than English, attachments, screenshots, voice.
- Account data errors. The entitlement tool is assumed correct; a wrong plan in the account system produces a confidently wrong answer.
- Adversarial inputs beyond two injection cases; one of them is caught by a regex before any model runs.
- Load. Latency and cost are measured one ticket at a time; concurrency is only modelled in the 10x plan.
- Tone and brand voice beyond the judge's one-line rubric.

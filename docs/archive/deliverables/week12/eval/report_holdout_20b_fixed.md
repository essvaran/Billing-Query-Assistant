# Integrated eval report (holdout_20b_fixed)

- Cases: **n = 15**  |  passed all assertions: **8 (53%)**
- Configuration: full system (version filter and policy guard on)
- Corpus and tickets are SYNTHETIC (see data/variant_a/synthetic/README.md).

## Pass rate by slice

| Slice | Passed | n | Rate |
|---|---|---|---|
| holdout | 8 | 15 | 53% |

## Both refund-policy versions live (the slice the brief asks about, not the average)

- Cases: 0/0 pass (n/a)
- Legacy 14-day customers: 0/0
- Current 30-day customers: 0/0
- Question pairs where BOTH customers got the right answer: 0/0

## Superseded-policy citation (the named metric)

- Refund cases expected to be answered: 0; answered: 0
- Final answers citing the wrong policy version: **0/0** (rate n/a)
- Drafts the guard blocked for the wrong version or window: 0
- Attempted rate (shown + blocked) over refund cases: None

## Failure modes (computed from assertions; trace ids are for reading)

| Mode | Count | % of n | Severity | Cases | Example trace |
|---|---|---|---|---|---|
| over_escalation | 4 | 27% | medium | HLD02, HLD03, HLD10, HLD14 | 335e9753abab4517b1af78dac329a4cc |
| wrong_source_cited | 3 | 20% | medium | HLD04, HLD08, HLD12 | 21c445c6fec744d0bfc3ad779adb1696 |

## Trajectory (tool choice) and the outcome-vs-trajectory gap

- Cases with an expected tool path: n = 15
- Tool-choice accuracy: **100%**; outcome accuracy: **53%**
- Gap (outcome minus trajectory): **-46.7 points**
- Right answer by the wrong path (lucky): 0; right path, wrong answer: 7; both right: 8; both wrong: 0
- Search calls beyond the cap of 2 that the agent tried anyway: 1

## Cost and latency

- Total cost for the run: $0.010821  |  mean per ticket: $0.000721
- Tickets that used no model call (pre-guard escalations): 0 of 15
- Deflected tickets (answered and all assertions pass): 8; cost per deflected ticket: **$0.001353** (all spend divided by deflected, escalations included)
- With the judge also GOOD: 0 tickets; $None each
- Model tickets: 15; mean 6831 tokens each; latency p50 2.0 s, p95 2.9 s (first ticket, which pays the cold start: 16.1 s)
- Free-tier ceiling: 8,000 tokens per minute / 6831 = **1.17 tickets per minute**
- **Latency caveat:** 51 of 51 model calls in this run were served from the response cache, so the latency figures above are NOT representative (cost uses the original token counts and is unaffected). Use an uncached run for latency.

## Judge

- Model: None (agent is a different family). Judged answers: 0 (GOOD 0, NOT_GOOD 0, error 0)
- **Agreement with human labels: NOT MEASURED** (no labelled cases matched judged cases). Label evaluation/integrated/labels.json using deliverables/week12/eval/label_sheet.md, then rerun. Until then no agreement number may be quoted.

## Assertion pass rates

| Check | Passed | n |
|---|---|---|
| cites_gold_source | 8 | 15 |
| decision_matches | 11 | 15 |
| expected_tools_called | 15 | 15 |
| has_valid_citation | 11 | 15 |
| no_money_claim | 11 | 11 |
| no_pii_in_reply | 11 | 11 |
| no_superseded_citation | 15 | 15 |
| order_status_grounded | 3 | 3 |
| shipping_days_correct | 1 | 4 |

## Failed cases

- **HLD02** (holdout), decision ESCALATE, trace `335e9753abab4517b1af78dac329a4cc`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted shipping-sla-matrix, cited []); shipping_days_correct (reply should say 4 business days)
- **HLD03** (holdout), decision ESCALATE, trace `8c8c1f708bd34f6cb0781092c3064f7d`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted shipping-sla-matrix, cited []); shipping_days_correct (reply should say 6 business days)
- **HLD04** (holdout), decision ANSWER, trace `21c445c6fec744d0bfc3ad779adb1696`: cites_gold_source (wanted track-order-web, cited ['track-order-troubleshooting'])
- **HLD08** (holdout), decision ANSWER, trace `6319abee459b443aa53c5549219fd7b2`: cites_gold_source (wanted track-order-web, cited ['track-order-troubleshooting'])
- **HLD10** (holdout), decision ESCALATE, trace `2fe8eabf6d1847bb96a32b7baf7d7f4d`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted shipping-sla-matrix, cited []); shipping_days_correct (reply should say 6 business days)
- **HLD12** (holdout), decision ANSWER, trace `c9a592d0e67f4514b0ef3f037f24d09f`: cites_gold_source (wanted track-order-web, cited ['track-order-troubleshooting', 'shipping-sla-matrix'])
- **HLD14** (holdout), decision ESCALATE, trace `ca4cfc4c713242c6b6ce9e1faff3538f`: decision_matches (expected ANSWER, got ESCALATE (tool_error)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted track-order-web, cited [])

## What this suite does NOT cover

- Multi-turn conversations. Every case is a single ticket; a customer who replies is not simulated (see the bonus second-contact eval).
- Real re-open behaviour. Deflection here means 'answered correctly by our assertions', not 'the customer did not write back'.
- Real help-centre language. The corpus and tickets are SYNTHETIC and templated, so retrieval scores are optimistic compared with real articles.
- Languages other than English, attachments, screenshots, voice.
- Account data errors. The entitlement tool is assumed correct; a wrong plan in the account system produces a confidently wrong answer.
- Adversarial inputs beyond two injection cases; one of them is caught by a regex before any model runs.
- Load. Latency and cost are measured one ticket at a time; concurrency is only modelled in the 10x plan.
- Tone and brand voice beyond the judge's one-line rubric.

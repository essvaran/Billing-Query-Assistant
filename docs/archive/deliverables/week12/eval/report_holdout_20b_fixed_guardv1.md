# Integrated eval report (holdout_20b_fixed)

- Cases: **n = 15**  |  passed all assertions: **7 (47%)**
- Configuration: full system (version filter and policy guard on)
- Corpus and tickets are SYNTHETIC (see data/variant_a/synthetic/README.md).

## Pass rate by slice

| Slice | Passed | n | Rate |
|---|---|---|---|
| holdout | 7 | 15 | 47% |

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
| over_escalation | 5 | 33% | medium | HLD01, HLD02, HLD03, HLD10, HLD14 | 0004ad35a83a40a68bd524710d0dd806 |
| wrong_source_cited | 3 | 20% | medium | HLD04, HLD08, HLD12 | fc7ebd9c25e74972a358a34844dbfddd |

## Trajectory (tool choice) and the outcome-vs-trajectory gap

- Cases with an expected tool path: n = 15
- Tool-choice accuracy: **100%**; outcome accuracy: **47%**
- Gap (outcome minus trajectory): **-53.3 points**
- Right answer by the wrong path (lucky): 0; right path, wrong answer: 8; both right: 7; both wrong: 0
- Search calls beyond the cap of 2 that the agent tried anyway: 1

## Cost and latency

- Total cost for the run: $0.010821  |  mean per ticket: $0.000721
- Tickets that used no model call (pre-guard escalations): 0 of 15
- Deflected tickets (answered and all assertions pass): 7; cost per deflected ticket: **$0.001546** (all spend divided by deflected, escalations included)
- With the judge also GOOD: 0 tickets; $None each
- Model tickets: 15; mean 6831 tokens each; latency p50 59.5 s, p95 115.5 s (first ticket, which pays the cold start: 19.2 s)
- Free-tier ceiling: 8,000 tokens per minute / 6831 = **1.17 tickets per minute**

## Judge

- Model: None (agent is a different family). Judged answers: 0 (GOOD 0, NOT_GOOD 0, error 0)
- **Agreement with human labels: NOT MEASURED** (no labelled cases matched judged cases). Label evaluation/integrated/labels.json using deliverables/week12/eval/label_sheet.md, then rerun. Until then no agreement number may be quoted.

## Assertion pass rates

| Check | Passed | n |
|---|---|---|
| cites_gold_source | 7 | 15 |
| decision_matches | 10 | 15 |
| expected_tools_called | 15 | 15 |
| has_valid_citation | 10 | 15 |
| no_money_claim | 10 | 10 |
| no_pii_in_reply | 10 | 10 |
| no_superseded_citation | 15 | 15 |
| order_status_grounded | 3 | 3 |
| shipping_days_correct | 0 | 4 |

## Failed cases

- **HLD01** (holdout), decision ESCALATE, trace `0004ad35a83a40a68bd524710d0dd806`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted shipping-sla-matrix, cited []); shipping_days_correct (reply should say 6 business days)
- **HLD02** (holdout), decision ESCALATE, trace `eb6ed3ea422c44ac885c85671ede3772`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted shipping-sla-matrix, cited []); shipping_days_correct (reply should say 4 business days)
- **HLD03** (holdout), decision ESCALATE, trace `6990c1e606884ce7868e863a4a94fb13`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted shipping-sla-matrix, cited []); shipping_days_correct (reply should say 6 business days)
- **HLD04** (holdout), decision ANSWER, trace `fc7ebd9c25e74972a358a34844dbfddd`: cites_gold_source (wanted track-order-web, cited ['track-order-troubleshooting'])
- **HLD08** (holdout), decision ANSWER, trace `fd5c1224741644cc83d4820da7889dd1`: cites_gold_source (wanted track-order-web, cited ['track-order-troubleshooting'])
- **HLD10** (holdout), decision ESCALATE, trace `8224f3e97b864260ae9ecf40f4e9c215`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted shipping-sla-matrix, cited []); shipping_days_correct (reply should say 6 business days)
- **HLD12** (holdout), decision ANSWER, trace `d3692836190c4d96a36d43332a6a6263`: cites_gold_source (wanted track-order-web, cited ['track-order-troubleshooting', 'shipping-sla-matrix'])
- **HLD14** (holdout), decision ESCALATE, trace `e18753891f5940e6885cf65de7837768`: decision_matches (expected ANSWER, got ESCALATE (tool_error)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted track-order-web, cited [])

## What this suite does NOT cover

- Multi-turn conversations. Every case is a single ticket; a customer who replies is not simulated (see the bonus second-contact eval).
- Real re-open behaviour. Deflection here means 'answered correctly by our assertions', not 'the customer did not write back'.
- Real help-centre language. The corpus and tickets are SYNTHETIC and templated, so retrieval scores are optimistic compared with real articles.
- Languages other than English, attachments, screenshots, voice.
- Account data errors. The entitlement tool is assumed correct; a wrong plan in the account system produces a confidently wrong answer.
- Adversarial inputs beyond two injection cases; one of them is caught by a regex before any model runs.
- Load. Latency and cost are measured one ticket at a time; concurrency is only modelled in the 10x plan.
- Tone and brand voice beyond the judge's one-line rubric.

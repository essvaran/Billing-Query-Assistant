# Integrated eval report (pf10_on)

- Cases: **n = 10**  |  passed all assertions: **7 (70%)**
- Configuration: full system (version filter and policy guard on)
- Corpus and tickets are SYNTHETIC (see data/variant_a/synthetic/README.md).

## Pass rate by slice

| Slice | Passed | n | Rate |
|---|---|---|---|
| random | 7 | 10 | 70% |

## Both refund-policy versions live (the slice the brief asks about, not the average)

- Cases: 0/0 pass (n/a)
- Legacy 14-day customers: 0/0
- Current 30-day customers: 0/0
- Question pairs where BOTH customers got the right answer: 0/0

## Superseded-policy citation (the named metric)

- Refund cases expected to be answered: 2; answered: 2
- Final answers citing the wrong policy version: **0/2** (rate 0.0)
- Drafts the guard blocked for the wrong version or window: 0
- Attempted rate (shown + blocked) over refund cases: 0.0

## Failure modes (computed from assertions; trace ids are for reading)

| Mode | Count | % of n | Severity | Cases | Example trace |
|---|---|---|---|---|---|
| over_escalation | 2 | 20% | medium | RAN06, RAN10 | 2749a5fd5a984cb79973f80533f01ba6 |
| wrong_source_cited | 1 | 10% | medium | RAN02 | 4eba88ec616c48358721e1fb5843c50e |

## Trajectory (tool choice) and the outcome-vs-trajectory gap

- Cases with an expected tool path: n = 9
- Tool-choice accuracy: **100%**; outcome accuracy: **67%**
- Gap (outcome minus trajectory): **-33.3 points**
- Right answer by the wrong path (lucky): 0; right path, wrong answer: 3; both right: 6; both wrong: 0
- Search calls beyond the cap of 2 that the agent tried anyway: 1

### Choices the model made itself (prefetched calls excluded)

- Cases that reached the model: n = 9; of them, prefetched by code: 9
- Model tool-choice accuracy: **78%**; outcome accuracy on the same cases: **67%**; gap **-11.1 points**
- Right answer by the wrong path: 0; right path, wrong answer: 1; mean tool calls the model made: 1
- When code prefetches the entitlement check and first search, the combined tool-choice figure above is right by construction; this one is the honest measure of the model.

## Cost and latency

- Total cost for the run: $0.008457  |  mean per ticket: $0.000846
- Tickets that used no model call (pre-guard escalations): 1 of 10
- Deflected tickets (answered and all assertions pass): 6; cost per deflected ticket: **$0.001409** (all spend divided by deflected, escalations included)
- With the judge also GOOD: 0 tickets; $None each
- Model tickets: 9; mean 4912 tokens each; latency p50 57.1 s, p95 119.7 s (first ticket, which pays the cold start: 19.6 s)
- Free-tier ceiling: 8,000 tokens per minute / 4912 = **1.63 tickets per minute**

## Judge

- Model: None (agent is a different family). Judged answers: 0 (GOOD 0, NOT_GOOD 0, error 0)
- **Agreement with human labels: NOT MEASURED** (no labelled cases matched judged cases). Label evaluation/integrated/labels.json using deliverables/week12/eval/label_sheet.md, then rerun. Until then no agreement number may be quoted.

## Assertion pass rates

| Check | Passed | n |
|---|---|---|
| cites_gold_source | 6 | 9 |
| decision_matches | 8 | 10 |
| eligibility_consistent | 2 | 2 |
| escalation_reason_ok | 1 | 1 |
| expected_tools_called | 9 | 9 |
| handoff_created | 1 | 1 |
| has_valid_citation | 7 | 9 |
| names_policy_version | 2 | 2 |
| no_money_claim | 7 | 7 |
| no_pii_in_reply | 7 | 7 |
| no_superseded_citation | 9 | 9 |
| nothing_customer_facing | 1 | 1 |
| order_status_grounded | 2 | 2 |
| shipping_days_correct | 3 | 3 |
| states_correct_window | 2 | 2 |

## Failed cases

- **RAN02** (random), decision ANSWER, trace `4eba88ec616c48358721e1fb5843c50e`: cites_gold_source (wanted track-order-web, cited ['track-order-troubleshooting'])
- **RAN06** (random), decision ESCALATE, trace `2749a5fd5a984cb79973f80533f01ba6`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted loyalty-points-team, cited [])
- **RAN10** (random), decision ESCALATE, trace `521f0ecbc3ae4ec4a952f2fcc8a8578d`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted track-order-web, cited [])

## What this suite does NOT cover

- Multi-turn conversations. Every case is a single ticket; a customer who replies is not simulated (see the bonus second-contact eval).
- Real re-open behaviour. Deflection here means 'answered correctly by our assertions', not 'the customer did not write back'.
- Real help-centre language. The corpus and tickets are SYNTHETIC and templated, so retrieval scores are optimistic compared with real articles.
- Languages other than English, attachments, screenshots, voice.
- Account data errors. The entitlement tool is assumed correct; a wrong plan in the account system produces a confidently wrong answer.
- Adversarial inputs beyond two injection cases; one of them is caught by a regex before any model runs.
- Load. Latency and cost are measured one ticket at a time; concurrency is only modelled in the 10x plan.
- Tone and brand voice beyond the judge's one-line rubric.

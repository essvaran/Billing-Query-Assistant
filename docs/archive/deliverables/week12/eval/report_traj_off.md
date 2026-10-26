# Integrated eval report (traj_off)

- Cases: **n = 20**  |  passed all assertions: **16 (80%)**
- Configuration: ABLATED: prefetch
- Corpus and tickets are SYNTHETIC (see data/variant_a/synthetic/SYNTHETIC.txt).

## Pass rate by slice

| Slice | Passed | n | Rate |
|---|---|---|---|
| random | 16 | 20 | 80% |

## Both refund-policy versions live (the slice the brief asks about, not the average)

- Cases: 0/0 pass (n/a)
- Legacy 14-day customers: 0/0
- Current 30-day customers: 0/0
- Question pairs where BOTH customers got the right answer: 0/0

## Superseded-policy citation (the named metric)

- Refund cases expected to be answered: 4; answered: 4
- Final answers citing the wrong policy version: **0/4** (rate 0.0)
- Drafts the guard blocked for the wrong version or window: 0
- Attempted rate (shown + blocked) over refund cases: 0.0

## Failure modes (computed from assertions; trace ids are for reading)

| Mode | Count | % of n | Severity | Cases | Example trace |
|---|---|---|---|---|---|
| over_escalation | 2 | 10% | medium | RAN10, RAN14 | d9d40a9c3f8c44018c23c553d856f685 |
| wrong_source_cited | 1 | 5% | medium | RAN02 | 3c6b3e1aeefe4b3ba2c10727e65cc3dc |
| other | 1 | 5% | low | RAN05 | 788ac100640040e3b7b1a1e57212a436 |

## Trajectory (tool choice) and the outcome-vs-trajectory gap

### Headline: choices the model made itself (prefetched calls excluded)

- Cases that reached the model: n = 16; of them, prefetched by code: 0
- Model tool-choice accuracy: **94%**; outcome accuracy on the same cases: **75%**; gap **-18.8 points**
- Right answer by the wrong path: 0; right path, wrong answer: 3; mean tool calls the model made: 2.19

### Combined, including calls prefetched by code (right by construction when prefetch is on)

- Cases with an expected tool path: n = 16
- Tool-choice accuracy: **100%**; outcome accuracy: **75%**
- Gap (outcome minus trajectory): **-25.0 points**
- Right answer by the wrong path (lucky): 0; right path, wrong answer: 4; both right: 12; both wrong: 0
- Search calls beyond the cap of 2 that the agent tried anyway: 0

## Cost and latency

- Total cost for the run: $0.018707  |  mean per ticket: $0.000935
- Tickets that used no model call (pre-guard escalations): 4 of 20
- Deflected tickets (answered and all assertions pass): 12; cost per deflected ticket: **$0.001559** (all spend divided by deflected, escalations included)
- With the judge also GOOD: 0 tickets; $None each
- Model tickets: 16; mean 6115 tokens each; latency p50 60.5 s, p95 62.8 s (first ticket, which pays the cold start: 18.6 s)
- Free-tier ceiling: 8,000 tokens per minute / 6115 = **1.31 tickets per minute**

## Judge

- **Primary:** rubric `v3b-integrated` on None (agent is a different family). Judged answers: 0 (GOOD 0, NOT_GOOD 0, error 0)
  - **Agreement with human labels: NOT MEASURED** (no labelled cases matched judged cases). A person labels the replies on the admin page /label; then `python -m tier1 eval --rescore <tag>`. Until then no agreement number may be quoted.


## Assertion pass rates

| Check | Passed | n |
|---|---|---|
| cites_gold_source | 14 | 16 |
| decision_matches | 18 | 20 |
| eligibility_consistent | 4 | 4 |
| escalation_reason_ok | 4 | 4 |
| expected_tools_called | 16 | 16 |
| handoff_created | 4 | 4 |
| has_valid_citation | 15 | 16 |
| names_policy_version | 4 | 4 |
| no_money_claim | 14 | 14 |
| no_pii_in_reply | 14 | 14 |
| no_superseded_citation | 16 | 16 |
| nothing_customer_facing | 4 | 4 |
| order_status_grounded | 2 | 3 |
| shipping_days_correct | 3 | 3 |
| states_correct_window | 4 | 4 |

## Failed cases

- **RAN02** (random), decision ANSWER, trace `3c6b3e1aeefe4b3ba2c10727e65cc3dc`: cites_gold_source (wanted track-order-web, cited ['track-order-troubleshooting'])
- **RAN05** (random), decision ANSWER, trace `788ac100640040e3b7b1a1e57212a436`: order_status_grounded (reply says 'shipped'; the order record says 'delivered')
- **RAN10** (random), decision ESCALATE, trace `d9d40a9c3f8c44018c23c553d856f685`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted track-order-web, cited [])
- **RAN14** (random), decision ESCALATE, trace `f7041a19f4b842b08db1910db5cb25cf`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source))

## What this suite does NOT cover

- Multi-turn conversations. Every case is a single ticket; a customer who replies is not simulated (see the bonus second-contact eval).
- Real re-open behaviour. Deflection here means 'answered correctly by our assertions', not 'the customer did not write back'.
- Real help-centre language. The corpus and tickets are SYNTHETIC and templated, so retrieval scores are optimistic compared with real articles.
- Languages other than English, attachments, screenshots, voice.
- Account data errors. The entitlement tool is assumed correct; a wrong plan in the account system produces a confidently wrong answer.
- Adversarial inputs beyond two injection cases; one of them is caught by a regex before any model runs.
- Load. Latency and cost are measured one ticket at a time; concurrency is only modelled in the 10x plan.
- Tone and brand voice beyond the judge's one-line rubric.

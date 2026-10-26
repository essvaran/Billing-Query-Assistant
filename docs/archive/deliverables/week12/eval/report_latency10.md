# Integrated eval report (latency10)

- Cases: **n = 10**  |  passed all assertions: **4 (40%)**
- Configuration: full system (version filter and policy guard on)
- Corpus and tickets are SYNTHETIC (see data/variant_a/synthetic/SYNTHETIC.txt).

## Pass rate by slice

| Slice | Passed | n | Rate |
|---|---|---|---|
| random | 4 | 10 | 40% |

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
| over_escalation | 3 | 30% | medium | RAN06, RAN07, RAN10 | 5be45a0642fc4356ba14c8cf2f4dc873 |
| other | 2 | 20% | low | RAN05, RAN09 | 03b957b950704cb59b12430632bbb63b |
| wrong_source_cited | 1 | 10% | medium | RAN02 | 11d03f4c83da40da9a9a2c8000c68bfd |

## Trajectory (tool choice) and the outcome-vs-trajectory gap

### Headline: choices the model made itself (prefetched calls excluded)

- Cases that reached the model: n = 9; of them, prefetched by code: 9
- Model tool-choice accuracy: **89%**; outcome accuracy on the same cases: **33%**; gap **-55.6 points**
- Right answer by the wrong path: 0; right path, wrong answer: 5; mean tool calls the model made: 1

### Combined, including calls prefetched by code (right by construction when prefetch is on)

- Cases with an expected tool path: n = 9
- Tool-choice accuracy: **100%**; outcome accuracy: **33%**
- Gap (outcome minus trajectory): **-66.7 points**
- Right answer by the wrong path (lucky): 0; right path, wrong answer: 6; both right: 3; both wrong: 0
- Search calls beyond the cap of 2 that the agent tried anyway: 2

With prefetch OFF the model makes every call itself (run `traj_off`, `report_traj_off.md`): n = 16, model tool-choice accuracy **94%**, outcome accuracy **75%**, gap **-18.8 points**, 2.19 tool calls per ticket.

## Cost and latency

- Total cost for the run: $0.008704  |  mean per ticket: $0.00087
- Tickets that used no model call (pre-guard escalations): 1 of 10
- Deflected tickets (answered and all assertions pass): 3; cost per deflected ticket: **$0.002901** (all spend divided by deflected, escalations included)
- With the judge also GOOD: 0 tickets; $None each
- Model tickets: 9; mean 5065 tokens each; latency p50 57.1 s, p95 120.1 s (first ticket, which pays the cold start: 18.1 s)
- Free-tier ceiling: 8,000 tokens per minute / 5065 = **1.58 tickets per minute**

## Judge

- **Primary:** rubric `v3b-integrated` on None (agent is a different family). Judged answers: 0 (GOOD 0, NOT_GOOD 0, error 0)
  - **Agreement with human labels: NOT MEASURED** (no labelled cases matched judged cases). A person labels the replies on the admin page /label; then `python -m tier1 eval --rescore <tag>`. Until then no agreement number may be quoted.


## Assertion pass rates

| Check | Passed | n |
|---|---|---|
| cites_gold_source | 5 | 9 |
| decision_matches | 7 | 10 |
| eligibility_consistent | 2 | 2 |
| escalation_reason_ok | 1 | 1 |
| expected_tools_called | 9 | 9 |
| handoff_created | 1 | 1 |
| has_valid_citation | 6 | 9 |
| names_policy_version | 2 | 2 |
| no_money_claim | 6 | 6 |
| no_pii_in_reply | 6 | 6 |
| no_superseded_citation | 9 | 9 |
| nothing_customer_facing | 1 | 1 |
| order_status_grounded | 1 | 3 |
| shipping_days_correct | 3 | 3 |
| states_correct_window | 2 | 2 |

## Failed cases

- **RAN02** (random), decision ANSWER, trace `11d03f4c83da40da9a9a2c8000c68bfd`: cites_gold_source (wanted track-order-web, cited ['track-order-troubleshooting', 'track-order-troubleshooting'])
- **RAN05** (random), decision ANSWER, trace `03b957b950704cb59b12430632bbb63b`: order_status_grounded (reply says 'shipped'; the order record says 'delivered')
- **RAN06** (random), decision ESCALATE, trace `5be45a0642fc4356ba14c8cf2f4dc873`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted loyalty-points-team, cited [])
- **RAN07** (random), decision ESCALATE, trace `c3f1df34318143039e03d554d891fcf9`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted webhooks-troubleshooting, cited [])
- **RAN09** (random), decision ANSWER, trace `6ad0917a2cdf4154b64bbf0daf960a4b`: order_status_grounded (reply says 'delivered' but the order was never looked up)
- **RAN10** (random), decision ESCALATE, trace `6968027e96fb4fa79bf4069086fa0ca5`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted track-order-web, cited [])

## What this suite does NOT cover

- Multi-turn conversations. Every case is a single ticket; a customer who replies is not simulated (see the bonus second-contact eval).
- Real re-open behaviour. Deflection here means 'answered correctly by our assertions', not 'the customer did not write back'.
- Real help-centre language. The corpus and tickets are SYNTHETIC and templated, so retrieval scores are optimistic compared with real articles.
- Languages other than English, attachments, screenshots, voice.
- Account data errors. The entitlement tool is assumed correct; a wrong plan in the account system produces a confidently wrong answer.
- Adversarial inputs beyond two injection cases; one of them is caught by a regex before any model runs.
- Load. Latency and cost are measured one ticket at a time; concurrency is only modelled in the 10x plan.
- Tone and brand voice beyond the judge's one-line rubric.

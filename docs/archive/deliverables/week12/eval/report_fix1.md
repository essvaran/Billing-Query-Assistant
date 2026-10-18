# Integrated eval report (fix1)

- Cases: **n = 39**  |  passed all assertions: **36 (92%)**
- Configuration: full system (version filter and policy guard on)
- Corpus and tickets are SYNTHETIC (see data/variant_a/synthetic/README.md).

## Pass rate by slice

| Slice | Passed | n | Rate |
|---|---|---|---|
| random | 17 | 20 | 85% |
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
| over_escalation | 2 | 5% | medium | RAN06, RAN10 | 439ac60bea174fdc8a023c86c47cdab0 |
| wrong_source_cited | 1 | 3% | medium | RAN02 | 27eea8dc42a14b2f82c8ccf08e62abad |

## Trajectory (tool choice) and the outcome-vs-trajectory gap

- Cases with an expected tool path: n = 27
- Tool-choice accuracy: **100%**; outcome accuracy: **89%**
- Gap (outcome minus trajectory): **-11.1 points**
- Right answer by the wrong path (lucky): 0; right path, wrong answer: 3; both right: 24; both wrong: 0
- Search calls beyond the cap of 2 that the agent tried anyway: 2

### Choices the model made itself (prefetched calls excluded)

- Cases that reached the model: n = 30; of them, prefetched by code: 30
- Model tool-choice accuracy: **90%**; outcome accuracy on the same cases: **90%**; gap **0.0 points**
- Right answer by the wrong path: 1; right path, wrong answer: 1; mean tool calls the model made: 0.53
- When code prefetches the entitlement check and first search, the combined tool-choice figure above is right by construction; this one is the honest measure of the model.

## Cost and latency

- Total cost for the run: $0.021045  |  mean per ticket: $0.00054
- Tickets that used no model call (pre-guard escalations): 9 of 39
- Deflected tickets (answered and all assertions pass): 23; cost per deflected ticket: **$0.000915** (all spend divided by deflected, escalations included)
- With the judge also GOOD: 18 tickets; $0.001169 each
- Model tickets: 30; mean 3664 tokens each; latency p50 6.2 s, p95 56.7 s (first ticket, which pays the cold start: 16.9 s)
- Free-tier ceiling: 8,000 tokens per minute / 3664 = **2.18 tickets per minute**
- **Latency caveat:** 23 of 94 model calls in this run were served from the response cache, so the latency figures above are NOT representative (cost uses the original token counts and is unaffected). Use an uncached run for latency.

## Judge

- **Primary:** rubric `week6-v2r` on qwen/qwen3.8-27b (agent is a different family). Judged answers: 24 (GOOD 18, NOT_GOOD 6, error 0)
  - **Agreement with human labels: NOT MEASURED** (no labelled cases matched judged cases). A person labels the replies on the admin page /label; then `python -m tier1 eval --rescore <tag>`. Until then no agreement number may be quoted.
- **Second opinion:** rubric `v3b-integrated` on qwen/qwen3.8-27b (agent is a different family). Judged answers: 24 (GOOD 21, NOT_GOOD 3, error 0)
  - **Agreement with human labels: NOT MEASURED** (no labelled cases matched judged cases). A person labels the replies on the admin page /label; then `python -m tier1 eval --rescore <tag>`. Until then no agreement number may be quoted.
- The primary rubric is the Week 6 validated judge (`evaluation/judge_v2.txt`, agreement 24/25 = 96% (evaluation/labels_25.json, Week 6) on Week 6 replies). That number does not carry over: the Week 6 model is no longer available on this key, and integrated replies also rest on account facts, which are added as one context block.


## Assertion pass rates

| Check | Passed | n |
|---|---|---|
| cites_gold_source | 22 | 25 |
| decision_matches | 37 | 39 |
| eligibility_consistent | 11 | 11 |
| escalation_reason_ok | 13 | 13 |
| expected_tools_called | 27 | 27 |
| handoff_created | 13 | 13 |
| has_valid_citation | 24 | 26 |
| names_policy_version | 11 | 11 |
| no_money_claim | 24 | 24 |
| no_pii_in_reply | 24 | 24 |
| no_superseded_citation | 26 | 26 |
| nothing_customer_facing | 13 | 13 |
| order_status_grounded | 2 | 2 |
| shipping_days_correct | 6 | 6 |
| states_correct_window | 11 | 11 |

## Failed cases

- **RAN02** (random), decision ANSWER, trace `27eea8dc42a14b2f82c8ccf08e62abad`: cites_gold_source (wanted track-order-web, cited ['track-order-troubleshooting'])
- **RAN06** (random), decision ESCALATE, trace `439ac60bea174fdc8a023c86c47cdab0`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted loyalty-points-team, cited [])
- **RAN10** (random), decision ESCALATE, trace `816978a2e9d74af9bcbe29e5eeb5cf81`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted track-order-web, cited [])

## What this suite does NOT cover

- Multi-turn conversations. Every case is a single ticket; a customer who replies is not simulated (see the bonus second-contact eval).
- Real re-open behaviour. Deflection here means 'answered correctly by our assertions', not 'the customer did not write back'.
- Real help-centre language. The corpus and tickets are SYNTHETIC and templated, so retrieval scores are optimistic compared with real articles.
- Languages other than English, attachments, screenshots, voice.
- Account data errors. The entitlement tool is assumed correct; a wrong plan in the account system produces a confidently wrong answer.
- Adversarial inputs beyond two injection cases; one of them is caught by a regex before any model runs.
- Load. Latency and cost are measured one ticket at a time; concurrency is only modelled in the 10x plan.
- Tone and brand voice beyond the judge's one-line rubric.

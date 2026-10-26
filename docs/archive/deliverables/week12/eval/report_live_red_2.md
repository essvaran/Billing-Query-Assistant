# Integrated eval report (live_red_2)

- Cases: **n = 1**  |  passed all assertions: **1 (100%)**
- Configuration: ABLATED: macro_filter,error_code_prompt
- Corpus and tickets are SYNTHETIC (see data/variant_a/synthetic/SYNTHETIC.txt).

## Pass rate by slice

| Slice | Passed | n | Rate |
|---|---|---|---|
| random | 1 | 1 | 100% |

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
| (none) | 0 | 0% | | | |

## Trajectory (tool choice) and the outcome-vs-trajectory gap

### Headline: choices the model made itself (prefetched calls excluded)

- Cases that reached the model: n = 1; of them, prefetched by code: 1
- Model tool-choice accuracy: **100%**; outcome accuracy on the same cases: **100%**; gap **0.0 points**
- Right answer by the wrong path: 0; right path, wrong answer: 0; mean tool calls the model made: 0

### Combined, including calls prefetched by code (right by construction when prefetch is on)

- Cases with an expected tool path: n = 1
- Tool-choice accuracy: **100%**; outcome accuracy: **100%**
- Gap (outcome minus trajectory): **0.0 points**
- Right answer by the wrong path (lucky): 0; right path, wrong answer: 0; both right: 1; both wrong: 0
- Search calls beyond the cap of 2 that the agent tried anyway: 0

With prefetch OFF the model makes every call itself (run `traj_off`, `report_traj_off.md`): n = 16, model tool-choice accuracy **94%**, outcome accuracy **75%**, gap **-18.8 points**, 2.19 tool calls per ticket.

## Cost and latency

- Total cost for the run: $0.000475  |  mean per ticket: $0.000475
- Tickets that used no model call (pre-guard escalations): 0 of 1
- Deflected tickets (answered and all assertions pass): 1; cost per deflected ticket: **$0.000475** (all spend divided by deflected, escalations included)
- With the judge also GOOD: 0 tickets; $None each
- Model tickets: 1; mean 2404 tokens each; latency p50 0.0 s, p95 0.0 s (first ticket, which pays the cold start: 19.1 s)
- Free-tier ceiling: 8,000 tokens per minute / 2404 = **3.33 tickets per minute**

## Judge

- **Primary:** rubric `v3b-integrated` on None (agent is a different family). Judged answers: 0 (GOOD 0, NOT_GOOD 0, error 0)
  - **Agreement with human labels: NOT MEASURED** (no labelled cases matched judged cases). A person labels the replies on the admin page /label; then `python -m tier1 eval --rescore <tag>`. Until then no agreement number may be quoted.


## Assertion pass rates

| Check | Passed | n |
|---|---|---|
| cites_gold_source | 1 | 1 |
| decision_matches | 1 | 1 |
| expected_tools_called | 1 | 1 |
| has_valid_citation | 1 | 1 |
| no_money_claim | 1 | 1 |
| no_pii_in_reply | 1 | 1 |
| no_superseded_citation | 1 | 1 |

## Failed cases

- none

## What this suite does NOT cover

- Multi-turn conversations. Every case is a single ticket; a customer who replies is not simulated (see the bonus second-contact eval).
- Real re-open behaviour. Deflection here means 'answered correctly by our assertions', not 'the customer did not write back'.
- Real help-centre language. The corpus and tickets are SYNTHETIC and templated, so retrieval scores are optimistic compared with real articles.
- Languages other than English, attachments, screenshots, voice.
- Account data errors. The entitlement tool is assumed correct; a wrong plan in the account system produces a confidently wrong answer.
- Adversarial inputs beyond two injection cases; one of them is caught by a regex before any model runs.
- Load. Latency and cost are measured one ticket at a time; concurrency is only modelled in the 10x plan.
- Tone and brand voice beyond the judge's one-line rubric.

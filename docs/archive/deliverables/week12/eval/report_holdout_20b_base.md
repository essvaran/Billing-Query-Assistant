# Integrated eval report (holdout_20b_base)

- Cases: **n = 15**  |  passed all assertions: **6 (40%)**
- Configuration: ABLATED: macro_filter,error_code_prompt
- Corpus and tickets are SYNTHETIC (see data/variant_a/synthetic/README.md).

## Pass rate by slice

| Slice | Passed | n | Rate |
|---|---|---|---|
| holdout | 6 | 15 | 40% |

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
| over_escalation | 5 | 33% | medium | HLD02, HLD07, HLD10, HLD14, HLD15 | 08baa3f0536a4beaaedd4965b8fbd794 |
| wrong_source_cited | 4 | 27% | medium | HLD06, HLD08, HLD12, HLD13 | 6efb961e7f9a45079573b2bdf09e6fe2 |

## Trajectory (tool choice) and the outcome-vs-trajectory gap

- Cases with an expected tool path: n = 15
- Tool-choice accuracy: **100%**; outcome accuracy: **40%**
- Gap (outcome minus trajectory): **-60.0 points**
- Right answer by the wrong path (lucky): 0; right path, wrong answer: 9; both right: 6; both wrong: 0
- Search calls beyond the cap of 2 that the agent tried anyway: 2

## Cost and latency

- Total cost for the run: $0.010871  |  mean per ticket: $0.000725
- Tickets that used no model call (pre-guard escalations): 0 of 15
- Deflected tickets (answered and all assertions pass): 6; cost per deflected ticket: **$0.001812** (all spend divided by deflected, escalations included)
- With the judge also GOOD: 0 tickets; $None each
- Model tickets: 15; mean 6907 tokens each; latency p50 2.0 s, p95 3.2 s (first ticket, which pays the cold start: 16.3 s)
- Free-tier ceiling: 8,000 tokens per minute / 6907 = **1.16 tickets per minute**
- **Latency caveat:** 53 of 53 model calls in this run were served from the response cache, so the latency figures above are NOT representative (cost uses the original token counts and is unaffected). Use an uncached run for latency.

## Judge

- Model: None (agent is a different family). Judged answers: 0 (GOOD 0, NOT_GOOD 0, error 0)
- **Agreement with human labels: NOT MEASURED** (no labelled cases matched judged cases). Label evaluation/integrated/labels.json using deliverables/week12/eval/label_sheet.md, then rerun. Until then no agreement number may be quoted.

## Assertion pass rates

| Check | Passed | n |
|---|---|---|
| cites_gold_source | 6 | 15 |
| decision_matches | 10 | 15 |
| expected_tools_called | 15 | 15 |
| has_valid_citation | 10 | 15 |
| no_money_claim | 10 | 10 |
| no_pii_in_reply | 10 | 10 |
| no_superseded_citation | 15 | 15 |
| order_status_grounded | 3 | 3 |
| shipping_days_correct | 2 | 4 |

## Failed cases

- **HLD02** (holdout), decision ESCALATE, trace `08baa3f0536a4beaaedd4965b8fbd794`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted shipping-sla-matrix, cited []); shipping_days_correct (reply should say 4 business days)
- **HLD06** (holdout), decision ANSWER, trace `6efb961e7f9a45079573b2bdf09e6fe2`: cites_gold_source (wanted webhooks-troubleshooting, cited ['webhooks-web'])
- **HLD07** (holdout), decision ESCALATE, trace `b8ef00158f34408abef1592445cc0e14`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted service-status-team, cited [])
- **HLD08** (holdout), decision ANSWER, trace `94dcc70c2f93456a8435291a96a59e07`: cites_gold_source (wanted track-order-web, cited ['missing-package-web'])
- **HLD10** (holdout), decision ESCALATE, trace `0f0b54d143404835b1060a745788ac1a`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted shipping-sla-matrix, cited []); shipping_days_correct (reply should say 6 business days)
- **HLD12** (holdout), decision ANSWER, trace `9c68cf23071c415aaddf82933df96cf0`: cites_gold_source (wanted track-order-web, cited ['shipping-sla-matrix'])
- **HLD13** (holdout), decision ANSWER, trace `bd6ea42e9f1b4870bfd6e86c628fed72`: cites_gold_source (wanted password-reset-troubleshooting, cited ['password-reset-web', 'password-reset-mobile'])
- **HLD14** (holdout), decision ESCALATE, trace `39c86dfb9cfb485a8035c692e42009a1`: decision_matches (expected ANSWER, got ESCALATE (tool_error)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted track-order-web, cited [])
- **HLD15** (holdout), decision ESCALATE, trace `a27f5e04cc264bcea8003abd06d6b9a6`: decision_matches (expected ANSWER, got ESCALATE (no_reliable_source)); has_valid_citation (no citation resolved to a retrieved chunk); cites_gold_source (wanted enterprise-invoicing-web, cited [])

## What this suite does NOT cover

- Multi-turn conversations. Every case is a single ticket; a customer who replies is not simulated (see the bonus second-contact eval).
- Real re-open behaviour. Deflection here means 'answered correctly by our assertions', not 'the customer did not write back'.
- Real help-centre language. The corpus and tickets are SYNTHETIC and templated, so retrieval scores are optimistic compared with real articles.
- Languages other than English, attachments, screenshots, voice.
- Account data errors. The entitlement tool is assumed correct; a wrong plan in the account system produces a confidently wrong answer.
- Adversarial inputs beyond two injection cases; one of them is caught by a regex before any model runs.
- Load. Latency and cost are measured one ticket at a time; concurrency is only modelled in the 10x plan.
- Tone and brand voice beyond the judge's one-line rubric.

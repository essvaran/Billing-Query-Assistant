# Re-scored error taxonomy on the integrated system

Run `after` (full system, n = 39 cases, of which 25 are expected to be answered and 30 reach a model).
Counting is mechanical (`scripts/taxonomy_tally.py`); the names and severities come from reading the traces listed here.
Open any trace in the UI at `/trace/<id>` (team lead) or with `python scripts/export_trace.py <id>`.
All data is synthetic.

## The modes

| # | Mode | What happens | Frequency | Severity | One trace | Origin |
|---|---|---|---|---|---|---|
| 1 | **Wrong source: near-duplicate sibling** | The answer cites a sibling article (for example `change-address-web` when the ticket quotes an error code that only `change-address-troubleshooting` explains). The text reads plausibly; the facts can be those of the wrong variant. | 3 of 25 answerable (12%): RAN02, RAN06, RAN20 | medium | `3e247f3442c14efb83f4eab701589157` (RAN02) | retrieval and corpus |
| 2 | **Internal macro cited to a customer** | The answer cites a Zendesk macro, which is an agent template and not a customer document, and invents steps that are in no source ("Report an Issue", "2 business days"). | 1 of 25 (4%): RAN14 | high (invented content, internal source) | `152cbfbacf2e4048af807e9257d11d64` | retrieval |
| 3 | **Escalation after a failed search** | A status question ("Status of order O2xxx please") does not retrieve the right article. The assistant searches twice, finds nothing reliable, and escalates. Correct behaviour, expensive: about 11,500 tokens, roughly 2.3 times a normal ticket. | 1 of 25 (4%): RAN10 (about 11,500 tokens) | medium (cost and a missed deflection) | `0c376962bcb749f5adf7ec69c8649683` | retrieval and agent loop |
| 4 | **Unsupported detail** | The reply states something no source or record supports (an invented procedure, a guessed meaning for an error code). Assertions cannot see it; only the judge did. | 2 of 25 judged NOT_GOOD (8%): RAN06, RAN14 | high | `d3f9377500434fe69de12bddcadf40b6` (RAN06) | model |
| 5 | **Typographic noise defeats exact-match guards** (created by integration) | The model writes zero-width spaces, non-breaking hyphens and narrow no-break spaces into its text, including inside citation ids. Each part works alone; together a correct, cited shipping answer was blocked as "no citation", and a window check would have missed "14<non-breaking hyphen>day". | 24 of 39 replies (62%) and 24 of the 30 that reached a model (80%) contain such characters | was high (it blocked a correct answer, seam 12); low since the normaliser | `46532339dcdf4773acd6ee05c7ac3b3a` (RAN19: the citation contains the noise and still resolves) | integration: model output meets regex guards |
| 6 | **Token blow-up from repeated searching** | The model re-queries instead of answering. A prompt asking for "at most twice" was ignored (in an earlier run, ticket TK3277 made 4 searches and used 13,088 tokens); the cap is now enforced in code, so the attempts are refused, but the model still tries. | 3 of 30 model tickets attempted more than two searches or used over 9,000 tokens: RAN02 (11.8k tokens), RAN06 (8.8k), RAN10 (11.5k) | medium (cost, latency, rate limit) | `3e247f3442c14efb83f4eab701589157` | agent loop |

## What the mode created by integration shows

Mode 5 did not exist in any part on its own. The model's output was fine to read. The citation validator (Week 3), the
version-aware guard (Week 12) and the model each behaved as designed. The failure lived in the seam: a regular expression
written for ASCII met text that looked identical to a person and differed in bytes. It was found in a live run, not in a
unit test, because every unit test used ASCII. It generalises: any new guard that matches model text has to normalise first.

## Modes that were looked for and not seen

- **Wrong refund-policy version in a final answer: 0 of 10** refund answers, with the version filter and policy guard ON and also with them
  OFF. In 11 of 39 cases the unfiltered search did put the other policy in front of the model; it did not use it. This is the
  failure that caused the client's escalation, and in this sample (n = 10) the model's use of the entitlement tool already
  prevented it. The defences are insurance whose value this sample cannot show. See `seams.md` 34.
- **Obeying an injection: 0 of 2.** One is stopped by a pattern with no model call; the other was answered by applying the real policy
  (outside the window, not eligible) and ignoring the claimed authority.
- **Promising a refund, leaking personal data in a reply, escalating a case that must be answered by a person: 0 each.**

## Not covered by this taxonomy

Modes that only appear in multi-turn conversations, with real customers, with real help-centre text, or under load.

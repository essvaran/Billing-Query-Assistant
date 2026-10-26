# Re-scored error taxonomy on the integrated system

Run `fix1` (the current system on the production model: both source fixes and prefetch on; n = 39 cases, of which 25 are
expected to be answered and 30 reach a model). Report: `eval/report_fix1.md`.
Counting is mechanical (`python scripts/taxonomy_tally.py after fix1`); the names and severities come from reading the traces listed here.
Open any trace in the UI at `/trace/<id>` (team lead) or with `python scripts/export_trace.py <id>`.
All data is synthetic.

## The modes

| # | Mode | What happens | Frequency | Severity | One trace | Origin |
|---|---|---|---|---|---|---|
| 1 | **Wrong source: near-duplicate sibling** | The answer cites a sibling article (RAN02 cites `track-order-troubleshooting` where `track-order-web` answers the question). The text reads plausibly; the facts can be those of the wrong variant. | 1 of 25 answerable (4%): RAN02 | medium | `27eea8dc42a14b2f82c8ccf08e62abad` (RAN02) | retrieval and corpus |
| 2 | **Escalation after a failed search** | The assistant searches, finds nothing it can cite, and escalates with `no_reliable_source` on a ticket it should have answered. Safe, but a missed deflection, and expensive: RAN10 (order status) used 12,305 tokens, about 3.4 times the 3,664 mean of a model ticket. | 2 of 25 answerable (8%): RAN06, RAN10 | medium (cost and a missed deflection) | `816978a2e9d74af9bcbe29e5eeb5cf81` (RAN10) | retrieval and agent loop |
| 3 | **Unsupported detail** | The reply states something the judge could not find in the retrieved text (a navigation path, a 60-minute deadline read from a sentence that said something else, delivery days). Assertions cannot see it; only the judge does. The judge itself is not yet validated on integrated replies, and on RAN19 the stated delivery days pass the `shipping_days_correct` assertion, so some of these may be judge errors. | 6 of 24 judged answers (25%) called NOT_GOOD by the primary judge: RAN02, RAN07, RAN13, RAN14, RAN19, BOT02 | high if real (invented content sent to a customer) | `f9509081e41d477ab249579b83c12588` (RAN13) | model, and possibly the judge |
| 4 | **Typographic noise defeats exact-match guards** (created by integration) | The model writes zero-width spaces, non-breaking hyphens and narrow no-break spaces into its text, including inside citation ids. Each part works alone; together a correct, cited shipping answer was blocked as "no citation" (seam 12), and a window check would have missed "14<non-breaking hyphen>day" (seam 13). | 24 of 39 replies (62%) and 24 of the 30 that reached a model (80%) contain such characters | was high (it blocked a correct answer); low since the normaliser | `58f82a24bdf0429783844cb5349ffcf0` (RAN01: the reply carries the noise and its citation still resolves) | integration: model output meets regex guards |
| 5 | **Token blow-up from repeated searching** | The model re-queries instead of answering. The cap of two searches is enforced in code, so extra attempts are refused, but the model still tries and pays for each lap. | 2 of 30 model tickets (7%) tried more than two searches or used over 9,000 tokens: RAN10 (12,305 tokens), RAN16 (7,993 tokens, three searches, answered correctly) | medium (cost, latency, rate limit) | `3146e8f3a3c949b4ba3324e68782f408` (RAN16) | agent loop |

## How the counts moved from the run before the fixes

Against run `after` (same 39 cases, before the macro exclusion, the error-code query instruction and prefetch):
wrong-source answers fell from 5 to 1 (sibling 3 to 1, internal macro 1 to 0, other document 1 to 0), escalation after a
failed search rose from 1 to 2 (RAN06 moved from a wrong-sibling answer to an escalation), the judge's NOT_GOOD count rose
from 2 to 6 (a different rubric is primary now, `seams.md` 55, so these two counts are not comparable), and the
invisible-character rate is unchanged at 24 of 39. See `closed_loop.md` section 5.

## What the mode created by integration shows

Mode 4 did not exist in any part on its own. The model's output was fine to read. The citation validator (Week 3), the
version-aware guard (Week 12) and the model each behaved as designed. The failure lived in the seam: a regular expression
written for ASCII met text that looked identical to a person and differed in bytes. It was found in a live run, not in a
unit test, because every unit test used ASCII. It generalises: any new guard that matches model text has to normalise first.

## Modes that were looked for and not seen

- **Internal macro cited to a customer: 0 of 25** in `fix1` (1 of 25 in `after`, RAN14). Macros are now excluded from
  customer-facing search (`closed_loop.md` section 3).
- **Wrong refund-policy version in a final answer: 0 of 10** refund answers, with the version filter and policy guard ON and also with them
  OFF (run `before`). In 11 of 39 cases the unfiltered search did put the other policy in front of the model; it did not use it. This is the
  failure that caused the client's escalation, and in this sample (n = 10) the model's use of the entitlement tool already
  prevented it. The defences are insurance whose value this sample cannot show. See `seams.md` 34.
- **Obeying an injection: 0 of 2.** One is stopped by a pattern with no model call; the other was answered by applying the real policy
  (outside the window, not eligible) and ignoring the claimed authority.
- **Promising a refund, leaking personal data in a reply, escalating a case that must be answered by a person: 0 each.**

## Run-to-run variance: what one run hides

The counts above come from one run, `fix1`, in which 23 of 94 model calls were replayed from the response cache. Two later
runs with the cache off (2026-10-19) answered the same tickets again:

- `latency10` (RAN01 to RAN10, same system): **4 of 10 passed, against 7 of 10 in `fix1`**. RAN05 and RAN09 now failed
  `order_status_grounded` (RAN05 said "shipped" where the order record says "delivered"; RAN09 said "delivered" without
  ever looking the order up), and RAN07 escalated with
  `no_reliable_source` instead of answering.
- `traj_off` (RAN01 to RAN20, prefetch off): RAN05 failed `order_status_grounded` again, and RAN14 escalated with
  `no_reliable_source`.

So **ungrounded order status** (RAN05 in both uncached runs, RAN09 in one) is a candidate sixth mode that `fix1` did not
show, and mode 2 (escalation after a failed search) is more frequent than its 8% above. The frequencies in the table are
one draw; variance is not measured. A full uncached re-run (`fix2`) is planned to re-count them.

## Not covered by this taxonomy

Modes that only appear in multi-turn conversations, with real customers, with real help-centre text, or under load.

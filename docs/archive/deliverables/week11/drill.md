# Support drill: the refund answer nobody logged a trace id for

Complaint (verbatim, nothing else available): "a customer said it gave a wrong answer about refunds yesterday afternoon."

## Result

| Field | Value |
|---|---|
| Time to find (human, mm:ss) | **TO BE TIMED** by a named squadmate (see "What is still open") |
| Query execution time (measured) | 0.117 s (`time` on the command below) |
| Slice that found it | **time window + keyword on the output** (`final_answer` and `question`) |
| Found trace | `8ebfc75d-5499-4c3f-b606-2bb07a201a7c` (2026-10-11T14:32:17Z, prompt `v1`) |

## Command

```
python scripts/search_traces.py --after "2026-10-11 12:00" --before "2026-10-11 18:00" --keyword refund
```

Returned exactly 1 trace out of 220. The answer says "entitled to a full refund within 30 days", but the cited chunk
(`HC-BILL-006--when-a-rollback-is-possible--prose-001`) contains no refund policy and `citations_valid = 0`.

Slices available in `scripts/search_traces.py`: time (`--after/--before`), text in input or output (`--keyword`),
prompt version (`--prompt-version`), cost outlier (`--cost-above`), and unverified answers (`--bad-citations`).
`--bad-citations --after 2026-10-11 --before 2026-10-12` also finds it with no keyword at all.

## Log fields that cost time or are still missing (honest list)

- `user_id` / `session_id`: not logged. With a user the slice would be one customer, not "everyone yesterday".
- `ticket_id`: not logged, so a support ticket cannot be joined to a trace.
- Pre-retrieval gate and citation-validation latency: not logged as separate spans (only `retrieval_ms`, `generation_ms`).
- `final_answer` has no full-text index; `LIKE '%refund%'` is a scan. Fine at 220 rows, not at millions (use SQLite FTS5).
- Before this week the only store was `traces.jsonl` with no cost field and no index, so the same drill was a grep.

## What is still open

- The drill was planted by `scripts/plant_bad_trace.py`, not by a squadmate, so the mm:ss above is not yet a valid
  human-timed number. A squadmate should plant a second trace with a different timestamp, start a stopwatch on the
  complaint text, and record the time here. Under 5:00 passes the bar; otherwise name the missing field above.
- Bonus (not done): add `user_id`/`session_id` columns, have the squadmate plant a second answer, compare times.

## Prompt version bump and rollout (two lines)

- Bump `v1` to `v2` (`PROMPT_VERSION` in `src/generation/answer.py`; adds rule 7 in `src/generation/prompts.py`: no refund/fee/compensation claims unless a chunk states them). Canary: serve `v2` to about 10% of traffic and watch `prompt_version = 'v2'` traces for 1 hour; halt if the share of non-refusal answers with `citations_valid = 0` rises above the `v1` baseline.
- Rollback: set `PROMPT_VERSION = "v1"` and restore the old rule 5/6 text, then redeploy; both versions stay queryable in `traces.prompt_version`.

## Closing the loop (eval case, RED then GREEN)

New case `G07` in `evaluation/eval_set.jsonl` (linked to the trace above) plus a deterministic assertion
`refuses_corpus_gap` in `evaluation/assertions.py`. Full suite (26 cases), assertion pass counts:

| Run | Prompt | Suite pass | G01 | G07 |
|---|---|---|---|---|
| RED (`suite_red.txt`) | regression reintroduced, tagged `v1-regressed` | **18/26** | FAIL | FAIL |
| GREEN (`suite_green.txt`) | `v2` | **23/26** | pass | pass |

Per-case diff (from stored traces): G01, G02, G05, G06, G07 flipped FAIL to pass; nothing flipped pass to FAIL.
The remaining 3 (G03, G04, A05) fail identically in both runs: their `corpus_gap` expectation is stale, because the
retrieved chunks genuinely contain the answer (e.g. `HC-BILL-001--timeline--prose-001`, `...--pay-1007`). They were not
relabelled to force 26/26; that is a decision for the eval owner.

Caveat on what RED means: the fabricated 30-day refund is the planted trace. When the regression was reintroduced, the
model did not invent a refund; it answered "the documentation doesn't address refunds", which `refuses_corpus_gap`
rejects because it is not the canonical refusal. The RED therefore proves the format guard, not fabrication. Fabrication
is caught by the alert rule `blocklist_keyword` and the `--bad-citations` slice.

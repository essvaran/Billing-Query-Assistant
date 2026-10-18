# Integrated eval suite

Grades the whole Tier-1 system through its real entry point (`tier1.service.handle_ticket`), not the
parts. One command:

```
python -m tier1 eval --tag fix1           # all 39 cases plus regression cases, both judges; writes deliverables/week12/eval/
python -m tier1 eval --tag fix1 --resume  # continue a run the provider's daily cap stopped (same flags)
python -m tier1 eval --rescore fix1       # recompute summary, agreement and report from saved rows: no model calls
python -m tier1 eval --cases regression   # only cases created from reported failures; --case-id REG01 for one
python -m tier1 eval --only both_versions --no-judge
python -m tier1 eval --tag before --ablate version_filter,policy_guard
```

All data is SYNTHETIC. A full run takes about 20 to 30 minutes on the free tier (8,000 tokens per
minute). Reruns are fast: responses are cached in `.cache/llm/` (set `LLM_CACHE=off` to disable,
`LLM_CACHE=replay` to forbid network calls).

## What is in the 39 cases

| Slice | n | Why it exists |
|---|---|---|
| random | 20 | Drawn uniformly at random (seed 1212) from all 300 tickets. Not curated: it contains easy and hard tickets. |
| both_versions | 6 | The same refund question from a legacy 14-day customer and a current 30-day customer, three times. One wrong policy version flips the answer. |
| shipping | 3 | Three regions with different delivery SLAs. |
| escalate | 4 | Legal, chargeback, safety, fraud. These must never be answered. |
| not_tier1 | 2 | Requests that are not support questions. |
| injection | 2 | The brief's literal injection (caught by a pattern, no model call) and one worded to get past the patterns. |
| missing_order | 2 | An order id that does not exist. |

Regenerate with `python evaluation/integrated/build_cases.py` (deterministic).

## Order of evaluation

1. **Assertions** (`assertions.py`): exact checks. Decision, escalation reason, handoff row, tools called,
   citation present and valid, policy version named and correct, window and eligibility stated correctly,
   shipping days correct, no refund promise, no PII in the reply. A case passes only if all pass.
2. **Judges** (`judge.py`), only on replies the system chose to answer, both on `qwen/qwen3.8-27b` (a different
   model family from the gpt-oss agent):
   - primary: the **Week 6 validated rubric** (`evaluation/judge_v2.txt`, 24/25 agreement on Week 6 replies), criteria
     verbatim, with the account facts added as one context block and the answer format changed from one word to a
     verdict plus a reason (rubric `week6-v2r`; the one-word format called every reply NOT_GOOD on qwen, seam 55). The
     Week 6 model is no longer on this key, so its old agreement does not carry over;
   - second opinion: the integrated rubric (`v3b-integrated`).
3. **Agreement**: the judge is only trusted once it matches human labels (target 85% or more, at least 20 labels).

## Labelling (a human has to do this)

The suite cannot label itself. After a full run:

1. A person who has worked a support queue signs in as admin and opens **Label replies** (`/label`). It shows each
   answered reply with the ticket, the account facts and the sources, and hides the judges' verdicts and the assertion
   results so they cannot anchor the label. Keys: G good, N not good, S skip.
2. Each label is saved to `labels.json` together with a hash of the reply it was given for (`labels.py`), so a label
   never grades a different reply from a later run.
3. After 20 labels the page shows agreement per judge. `python -m tier1 eval --rescore <tag>` writes it into the
   report: the number, how many labels it rests on, who labelled, and how often the judge approved a reply the human
   rejected.

`deliverables/week12/eval/label_sheet.md` is the same content as a file for reading offline; record the labels on the page so each is tied to its reply.

Until labels exist the report prints "NOT MEASURED". Do not quote an agreement figure before then.

## Before and after

`--ablate` switches defences off so the same cases show what the number was without them:

- `version_filter`: the help-centre server ignores `policy_version`, so both refund policies are searchable.
- `policy_guard`: the post-guard stops checking the cited version and the stated window.
- `macro_filter`, `error_code_prompt`: the two source fixes from the closed loop.
- `prefetch`: the model makes the entitlement check and first search itself (the trajectory section then reports the
  model's own tool choices for both settings).

These flags are test seams. Never set `TIER1_ABLATE` in production.

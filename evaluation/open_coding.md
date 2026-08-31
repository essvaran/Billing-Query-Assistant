# Open Coding — Failed Traces (Sample, seed = 80)

**Analyst:** Essvaran  
**Date:** 2026-08-25  
**Sample:** 20 traces, `random.seed(80)`, hybrid BM25+RRF retriever only  
**Scope:** 4 traces where `citations_valid = False`

---

> **What open coding means here.**  
> I read each failing trace cold — question, retrieved chunks, raw model output — and wrote down what I actually noticed, not what I hoped to see. No fixes, no re-runs. The goal is to understand *why* things went wrong before deciding whether to change anything.

---

## Failure #1 — Multi-Part Question, Partial Evidence, Total Refusal

**Trace ID:** `12293f50`  
**Question:** *What is ERR-4032 and how long does it take to resolve?*  
**Query type:** Multi-part  
**Model output:** `I cannot answer that from the indexed help-centre articles.`

### What the retriever gave the model

| Rank | Chunk ID | Relevance |
|------|----------|-----------|
| 1 | `HC-BILL-002--frequently-asked-questions-about-error-codes--prose-001` | Partial — general FAQ, not ERR-4032 specific |
| 2 | `HC-BILL-002--error-codes--err-4032` | Direct hit — this IS the ERR-4032 article |
| 3 | `HC-BILL-002--error-codes--err-5010` | Irrelevant — a completely different error code |

### What I noticed

The answer to "what is ERR-4032?" is sitting right there in chunk #2. If you asked only that first sub-question, the model would almost certainly have answered it. But the question also asks *how long does it take to resolve?* — and that resolution time detail is not clearly stated in any of the three chunks. The model faced a two-part question where one half had evidence and the other didn't.

What it did instead of partially answering was refuse completely. It treated the question as a single unit and, finding the full question unanswerable, refused everything.

Chunk #3 made things worse. ERR-5010 has nothing to do with ERR-4032 — it is a different error, different section, different resolution path. Having that chunk in context likely reinforced the model's sense that the retrieved material was fragmented and not covering the actual question.

### Root cause

Two things stacked: the question was multi-part (the model is stricter when it cannot answer all sub-parts), and an irrelevant chunk at rank 3 created noise that undermined confidence in the context overall. The relevant article was present but the model chose full refusal over a partial answer.

**Failure type: False refusal — context interference + multi-part query sensitivity**

---

## Failure #2 — Correct Refusal, Wrong Retrieval

**Trace ID:** `454cd6b4`  
**Question:** *How do I set a default payment method?*  
**Query type:** Semantic  
**Model output:** `I cannot answer that from the indexed help-centre articles.`

### What the retriever gave the model

| Rank | Chunk ID | Relevance |
|------|----------|-----------|
| 1 | `HC-BILL-002--payment-method-error-codes-pay-series--pay-1001` | None — PAY-1001 error code, not setup |
| 2 | `HC-BILL-003--payment-method-errors-during-migration--err-4040` | None — migration error code |
| 3 | `HC-BILL-002--error-codes--err-4040` | None — error code reference |

### What I noticed

This is the one case where the model's refusal was actually the *right* call. All three chunks the retriever surfaced are about payment method **error codes** — PAY-1001, ERR-4040. None of them explain how to navigate to the payment settings screen and set a default. The user is asking a setup/workflow question and got error-code documentation.

The hybrid retriever latched onto the phrase "payment method" in both the query and the chunk metadata and brought back everything tagged with that term — but "payment method" appears in error code articles far more frequently than in the setup guides, so the setup guide lost out.

The model did exactly what it should: it read the context, saw none of it answered the question, and refused. The failure is entirely upstream — the retriever never found the right document and the answer was not even available in any doc.

### Root cause

Vocabulary mismatch between the question and the indexed document. The user's intent is about a UI action ("set a default"), but the knowledge base's payment-related articles are dominated by error code terminology. A keyword like "default payment" or "payment settings" would need to appear in the right chunk for BM25 to surface it. If that guide is not in the corpus or is indexed with different terms, no amount of re-ranking fixes this.

**Failure type: Retrieval gap — semantic intent not covered by indexed vocabulary**

---

## Failure #3 — Good Answer, Broken Citations

**Trace ID:** `082a861f`  
**Question:** *What should I do when migration fails on the same step three times?*  
**Query type:** Simple (procedural)  
**Model output:** *(substantively correct — model gave escalation steps)*

### What the retriever gave the model

| Rank | Chunk ID | Relevance |
|------|----------|-----------|
| 1 | `HC-BILL-002--frequently-asked-questions-about-error-codes--prose-001` | Weak — error FAQ, tangentially relevant |
| 2 | `HC-BILL-006--escalating-to-support--prose-001` | Strong — escalation guide |
| 3 | `HC-BILL-002--escalation-decision-tree--prose-001` | Strong — decision tree for when to escalate |

### What the model actually said

> *"If the same migration error appears on the same step after you have retried twice, you should escalate the issue to billing support. Open a support ticket and include: 1. Account ID... 2. Exact error code... 3. Migration stage... This follows the escalation rule: 'The same migration error code recurs after two retry attempts' → open a support ticket.  **[HC-BILL-006] [HC-BILL-002--escalation-decision-tree]***"

### What I noticed

The answer is genuinely good. The model read the escalation guide and the decision tree, synthesised the rule correctly ("same error after two retries → open a ticket"), gave sensible instructions about what to include in the ticket, and even quoted the decision tree trigger condition.

But the citations failed. Look at what it wrote: `[HC-BILL-006]` and `[HC-BILL-002--escalation-decision-tree]`. The actual chunk IDs are `HC-BILL-006--escalating-to-support--prose-001` and `HC-BILL-002--escalation-decision-tree--prose-001`. The model abbreviated both — it kept the article identifier but dropped the section and prose suffixes.

The citation validator checks for exact chunk ID matches. Shortened IDs do not match, so both citations fail validation even though the model cited the correct *articles*. The answer was right. The citation format was wrong.

### Root cause

The model understands which source it is drawing from but renders the citation in a shortened, human-readable form rather than the full chunk ID format. This is a systemic formatting issue — the prompt probably does not strongly enough enforce that the full chunk ID string (including section and `--prose-001` suffix) must be reproduced verbatim.

**Failure type: Citation format mismatch — abbreviated chunk IDs fail exact-match validation**

---

## Failure #4 — Right Answer, Wrong Dash Character

**Trace ID:** `2a1b4099`  
**Question:** *Payment method re-verification failed during migration*  
**Query type:** Simple (implicit — this is a problem statement, not a direct question)  
**Model output:** *(substantively correct — correctly identified ERR-4040)*

### What the retriever gave the model

| Rank | Chunk ID | Relevance |
|------|----------|-----------|
| 1 | `HC-BILL-001--appendix-c-migration-error-code-quick-reference--err-4040` | Strong — quick reference for ERR-4040 |
| 2 | `HC-BILL-003--payment-method-errors-during-migration--err-4310` | Weak — different error code (ERR-4310) |
| 3 | `HC-BILL-003--payment-method-errors-during-migration--err-4040` | Strong — ERR-4040 migration details |

### What the model actually said

> *"The 'payment method re-verification failed' issue corresponds to error code ERR-4040. Cause: The legacy payment method on file could not be re-verified with the card network. Fix: Add a new payment method and set it as the default before retrying the migration. Blocking: Yes.*
> *[HC-BILL-001**–**appendix-c-migration-error-code-quick-reference**–**err-4040] [HC-BILL-003**–**payment-method-errors-during-migration**–**err-4040]*"

### What I noticed

The model got everything right — it identified ERR-4040 correctly, explained the cause, gave the fix, flagged it as a migration blocker. The two chunk IDs it cited are both in the retrieved set. On the surface this should pass.

But look at the separator characters. The real chunk IDs use double hyphens (`--`) as separators. The model output uses **en-dashes** (`–`, Unicode U+2013). They look almost identical on screen but are different characters. The citation validator does a string comparison, so `HC-BILL-001–appendix-c` ≠ `HC-BILL-001--appendix-c`. Every citation fails.

This is a subtle Unicode substitution — the kind of thing that slips through human review but breaks automated validation. The question being phrased as a problem statement rather than a direct question is also worth noting: the model interpreted the implicit intent correctly ("they want to know what this error is and how to fix it") which shows reasonable pragmatic reasoning, but it still couldn't get the citation characters right.

### Root cause

The model replaced double hyphens with en-dashes when formatting citations, likely because en-dashes look typographically cleaner. The citation validation has no tolerance for this substitution. A normalisation step (strip and compare after replacing `–` and `—` with `--`) in the validator would make this class of failure disappear entirely.

**Failure type: Citation character error — en-dash (–) substituted for double hyphen (--)**

---

## Summary

| # | Question (short) | Failure type |
|---|-----------------|--------------|
| 1 | What is ERR-4032 and how long to resolve? | False refusal — multi-part + context noise |
| 2 | How do I set a default payment method? | Retrieval gap — wrong documents surfaced |
| 3 | Migration fails on same step three times? | Citation format — abbreviated chunk IDs |
| 4 | Payment method re-verification failed | Citation character — en-dash vs double hyphen |

### What stands out across all four

Two of the four failures (#3 and #4) produced correct, useful answers — they only failed because the citation format didn't match what the validator expected. The answer quality was fine; the post-processing was not. That is a different kind of problem than #1 and #2, which involve genuine knowledge retrieval gaps.

Failure #1 and #2 are retrieval problems. The system either retrieved the wrong chunks entirely (no relevant document for "set a default payment method") or retrieved the right chunk but let irrelevant noise undermine it. These require changes at the retrieval or knowledge-base level to fix.

Failures #3 and #4 are citation correctness problems that could be addressed by making the citation instructions in the system prompt more explicit, or by adding normalisation to the validator. The underlying RAG pipeline worked — the retriever found the right chunks, the model synthesised the right answer. The last mile (formatting the citation exactly) is where it broke down.

---

## Failure Taxonomy — 20-Trace Sample (seed = 80)

> This table covers only the **20-trace random sample**. 4 of 20 traces failed (20% failure rate).

| Trace ID | Question | Mode | Count | Freq | Severity |
|----------|----------|------|------:|-----:|----------|
| `12293f50-961d-4153-8d27-4f67f3c04f15` | What is ERR-4032 and how long does it take to resolve? | False Refusal | 1 | 25% | Medium |
| `454cd6b4-689d-443a-a1aa-a27534e482a3` | How do I set a default payment method? | Corpus Gap | 1 | 25% | High |
| `082a861f-8e92-4c56-b169-1aa4d8b197fc` | What should I do when migration fails on the same step three times? | Citation Abbreviation | 1 | 25% | Medium |
| `2a1b4099-9225-430a-b679-61603985dde4` | Payment method re-verification failed during migration | Citation Character Error | 1 | 25% | Low |

**Count** — occurrences of this mode within the 20-trace sample.  
**Freq** — share of the 4 failed traces in the sample.

---

## Failure Taxonomy — Full Dataset (100 hybrid traces)

> Counts and frequencies are measured across **all 100 hybrid traces** (19 total failures), not just the 20-trace sample.

| Trace ID | Question | Mode | Count | Freq | Severity |
|----------|----------|------|------:|-----:|----------|
| `12293f50-961d-4153-8d27-4f67f3c04f15` | What is ERR-4032 and how long does it take to resolve? | False Refusal | 5 | 26% | Medium |
| `454cd6b4-689d-443a-a1aa-a27534e482a3` | How do I set a default payment method? | Corpus Gap | 8 | 42% | High |
| `082a861f-8e92-4c56-b169-1aa4d8b197fc` | What should I do when migration fails on the same step three times? | Citation Abbreviation | 5 | 26% | Medium |
| `2a1b4099-9225-430a-b679-61603985dde4` | Payment method re-verification failed during migration | Citation Character Error | 1 | 5% | Low |

**Count** — number of traces across the full 100-trace hybrid dataset where this failure mode was observed.  
**Freq** — count as a share of the 19 total failures (false refusal + corpus gap together account for 13 of 19 = 68%).  
**Severity** — impact on the end user if the system were in production.

### Severity rationale

| Mode | Count | Severity | Reason |
|------|------:|----------|--------|
| Corpus Gap | 8 | **High** | The document does not exist in the knowledge base at all. Every user asking these questions will be refused every time — no retrieval tuning or code fix resolves it. Requires new articles to be authored and ingested. |
| False Refusal | 5 | **Medium** | The correct chunk was retrieved but context noise or a multi-part question structure caused the model to refuse. The knowledge exists — a retrieval or prompt adjustment can surface it. |
| Citation Abbreviation | 5 | **Medium** | The model produced a correct, useful answer that was silently swapped for the refusal message because chunk IDs were shortened. The user received worse information than the model actually generated. A prompt or validator change resolves it. |
| Citation Character Error | 1 | **Low** | Same outcome as abbreviation — correct answer hidden by a single character difference (en-dash vs double hyphen). A one-line normalisation in the citation validator is the complete fix. |

# Week 6 Demo -- RAG Eval System

## What you're showing

An evaluation system for a billing-support RAG pipeline. The eval measures
whether the assistant (a) gives factually correct answers, (b) refuses
appropriately when the corpus has no answer, and (c) formats citations
correctly. It combines **deterministic assertions** (no LLM needed) with an
**LLM-as-judge** that is iterated across two prompt versions, and a **blind
human label** agreement check.

---

## Dashboard

Open: **`http://localhost:4200/eval`** (Angular app, already running)

No scripts to run -- all results are embedded in the UI for demo.

---

## Demo Script

### 1 -- Overview tab (2 min)

**Say:** "We built 25 test cases across 4 failure modes discovered through
open coding on real traces."

Point to the **5 stat cards**:
- 25 cases, 4 assertions, **88% combined pass rate**
- Judge alone: **88%** -- both v1 and v2 agree, 22/25 GOOD

Walk the **Eval Pipeline strip** left to right:
> "Generate answers -> 4 deterministic assertions -> *blind label* (commit before judge) -> LLM judge -> measure agreement"

Emphasis: the star step is step 3 -- human reads every answer and commits
`labels_25.json` to git *before* any judge prompt is written. That prevents
the judge from being tuned to match the corpus instead of your actual expectations.

Walk the **4 mode cards**:
- corpus_gap: 83% -- 5/6 correct; G04 cited wrong chunk
- false_refusal: 87% -- 7/8 correct; F06 judge strict on second citation
- citation_abbreviation: 100% -- all 6 correct; R01 now answers correctly
- citation_character_error: 80% -- 4/5 correct; CE02 hallucinated escalation steps

Point to **Regression cases**:
> "Both regression cases now pass. R01 was the exact question that first caught
> the bare-article-ID bug -- in the initial broken run the citation validator
> masked it as a false refusal. After the model switch (openai/gpt-oss-120b) and
> rate-limit fix, R01 now produces a correct answer with full chunk IDs. R02
> continues to pass as expected."

---

### 2 -- Case Explorer tab (2 min)

Click **Case Explorer**.

**Unfiltered view:** show the table. Point to the **Judge v1** and **Judge v2**
columns side by side -- each case now shows both verdict columns.

Click **citation_abbreviation** filter:
> "All 6 of these cases ask about specific codes or plans. The assertion
> that catches bare IDs is `no_bare_article_id` -- regex, no API call, instant.
> All 6 pass assertions AND judge in the clean run."

Click **false_refusal** filter. Point to F06:
> "F06 is the single judge/human disagreement. The judge says NOT_GOOD because
> the second citation (FAQ chunk) was seen as not explicitly supporting the
> claim. As a human reviewer, the core answer from HC-BILL-006 is clearly
> correct. This shows the judge is slightly over-penalising."

---

### 3 -- Assertions tab (2 min)

Click **Assertions**.

Walk the **4 assertion cards**:

**no_bare_article_id (25/25) -- all pass:**
> "In the broken run, R01 and F04 had bare citations in raw_answer but the
> citation validator converted them to refusals BEFORE assertions ran.
> In the clean run, the model produces full 3-part IDs so no masking occurs --
> the assert passes on real content, not on refusal messages."

**no_en_dash_in_citation (25/25) -- all pass:**
> "Same -- CE01 previously triggered the citation validator. Now the model
> outputs proper hyphens throughout."

**no_hallucinated_error_code (25/25) and no_fabricated_citation (25/25):**
> "Both pass clean. The corpus centroid gate and score threshold prevent
> the model from inventing codes or citing unretrieved chunks."

Point to the **Assertion Results by Mode table**:
> "All green. Previously we had a design insight: assertions on final_answer
> always looked clean because the citation validator sanitised upstream.
> In the clean run, the assertions are genuinely clean -- no sanitisation
> was needed."

---

### 4 -- Judge tab (3 min)

Click **Judge**.

**Failure Root Cause -- 3 cards:**
> "22 correct, 2 genuine model failures, 1 judge disagreement.
> The 17 infrastructure failures from the first run are gone -- fixed by
> adding a 5-second delay between calls and 429 retry-with-backoff."

Walk the 3 failure cards:
- G04: model cited the extended-FAQ chunk but that chunk doesn't mention pausing
- CE02: escalation step 2 adds menu paths and data fields not in the context
- F06: judge too strict -- human labels this GOOD

**Prompt Iteration section:**

Point to `JUDGE_V1.TXT`:
> "v1 prompt: GOOD/NOT_GOOD rules only. No few-shot. Result: 22/25 = 88%."

Point to `JUDGE_V2.TXT` (right card, few-shot highlighted in blue):
> "v2 adds a multi-part question rule and 2 few-shot examples from the v1
> disagreements in the broken run (G03 and R01). In the clean run, the
> few-shot calibration points are no longer edge cases -- both judges
> agree on them. Result: 22/25 = 88% -- identical to v1."

Walk the **v1 vs v2 Comparison table**:
> "Zero difference in the clean run -- both produce 22/25. The few-shot
> examples were calibrated for the broken run's edge cases. The clean run
> surfaces different failures (G04, CE02) that neither prompt was trained on."

Point to the **two agreement boxes**:
> "Both show 96% (24/25). The single disagreement is F06 --
> human says GOOD, both judges say NOT_GOOD. Agreement v1 = v2 = 96%."

Point to the **final combined table**:
> "88% overall. citation_abbreviation = 100%, corpus_gap = 83%,
> false_refusal = 87%, citation_character_error = 80%.
> All modes exceed the 80% target."

---

## One-command Demo (if running locally)

```bash
# Full clean eval with judge v2 (5s delay + 429 retry built in)
python evaluation/run_eval.py --judge-version v2

# Judge v1 only (skip answer generation -- use existing answers_25.jsonl)
python evaluation/run_eval.py --skip-generate --judge-version v1
```

Actual terminal output (clean run -- both v1 and v2):
```
Mode                      | N  | assert | judge | Pass%
corpus_gap                |  6 |   6/6  |  5/6  |  83%
false_refusal             |  8 |   8/8  |  7/8  |  87%
citation_abbreviation     |  6 |   6/6  |  6/6  | 100%
citation_character_error  |  5 |   5/5  |  4/5  |  80%
TOTAL                     | 25 |  25/25 | 22/25 |  88%
```

---

## Key talking points

| Point | One-liner |
|---|---|
| Why blind labeling? | Prevents the judge prompt from being reverse-engineered from the corpus |
| Why assertions + judge? | Assertions catch format bugs; judge catches factual failures -- complementary layers |
| Citation validator (old run) | R01, F04, CE01 had correct content but bad citations; validator returned refusal -- now fixed |
| What changed v1 to v2? | Multi-part question rule + 2 few-shot examples; same score (88%) on clean run because edge cases shifted |
| G04 failure | Wrong chunk cited -- model answered "cannot pause" but the cited chunk doesn't say that |
| CE02 failure | Hallucinated escalation steps (menu paths, data fields) not in retrieved context |
| F06 disagreement | Human says GOOD (core answer correct from HC-BILL-006); judge says NOT_GOOD (second citation not explicitly supporting) |
| Rate limit fix | 5s inter-call delay + 429 retry-backoff in llm_client.py -- 25/25 generated cleanly |
| 88% exceeds 80% target | System passes. Two genuine model failures (G04, CE02) are fixable with retrieval + prompt tuning. |

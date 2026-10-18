# Top known weaknesses

Draft prepared from the traces on **2026-10-16**, before any reviewer saw the system; evidence refreshed on
**2026-10-18** from the full production-model run `fix1`. It is written from evidence in
`eval/report_after.md`, `taxonomy.md` and `seams.md`. The owner should read it, change what they disagree with, and keep
their own date when they adopt it: the point of the list is that it was written before anyone asked.

## 1. I do not yet know whether the judge can be trusted

The judge (qwen/qwen3.8-27b) has never been compared with a person. Its verdicts moved a lot for a reason that had nothing
to do with answer quality: when it was given the order record it had been missing, NOT_GOOD fell from 5 to 2 (three of
the five were correct order statuses it called invented; see seam 31). That shows how fragile a judge number is.
Until someone who has worked a support queue labels the replies (`evaluation/integrated/labels.json`), every
"helpful" or "good" figure in the report is unvalidated, and the 85% agreement target is unmet by default.

It happened again on 2026-10-18: the Week 6 validated rubric, moved to the new judge model, called every integrated reply
NOT_GOOD while it was forced to answer in one word, and gave sensible verdicts once it could give one reason (`seams.md` 55).
On `fix1` the two judges disagree with each other on 3 of 24 replies (RAN02, RAN07, BOT02; primary GOOD 18, second opinion GOOD 21),
which is exactly why only a person can settle it.

*Evidence:* `eval/summary_after_run1_judge_without_order_facts.json` against `eval/summary_after.json`; `eval/report_fix1.md`, Judge.
*What I would do next:* one hour of labelling by a Tier-1 lead on `/label` (the 24 answered replies of `fix1`), then
`python -m tier1 eval --rescore fix1`, and read the disagreements, starting with any case where a judge said GOOD and the human said NOT_GOOD.

## 2. Retrieval picks the wrong article often enough to matter

5 of 25 answerable cases (20%) cited the wrong source: three cited a near-identical sibling article (RAN02, RAN06,
RAN20), one cited an internal Zendesk macro and invented steps that were in no source (RAN14), one cited the shipping
matrix instead of the delivery article (RAN19). Order-status questions are worse: the query "Status of order O2xxx
please" does not find the right article (retrieval hit@3 was 10 of 30), and the assistant spends about 11,500 tokens
searching before it escalates (RAN10), roughly 2.3 times a normal ticket.
The synthetic corpus makes sibling confusion look worse than it would be (four templated variants per topic differ only in
a few numbers), but real help centres also contain near-duplicates.

*Evidence:* traces `3e247f3442c14efb83f4eab701589157` (RAN02), `152cbfbacf2e4048af807e9257d11d64` (RAN14), `0c376962bcb749f5adf7ec69c8649683` (RAN10).
*Since then:* on the production model after the two source fixes and the token cut, wrong source fell from 6 to 3 of 25 on the same
cases (`closed_loop.md` section 5), but RAN02 still cites the sibling article, RAN10 (order status) still escalates after searching,
and RAN06 moved from a wrong-sibling answer to an escalation. On held-out tickets the fixes were inconclusive.

*What I would do next:* measure hit@3 on real articles before touching the chunker; see `closed_loop.md` for the two fixes already made and what they did.

## 3. The free tier is the capacity limit, and it is below today's volume

The provider caps this model at **200,000 tokens a day**. At about 6,300 tokens per ticket that reaches a model, that was roughly
40 tickets a day, against 67 a day at today's 2,000 a month. After the token cut (entitlement and first search in code) it is about
4,200 tokens and about 60 tickets a day: better, still below today's volume (`cost_and_10x.md`). I only learned the number when my own evaluation run was cut off
halfway: it is in no response header, only in the body of the 429 error. Behind it sit 1,000 requests a day (about 357 tickets)
and 8,000 tokens a minute (about 1.3 tickets a minute, so back-to-back tickets queue: p50 59 s, p95 119 s uncached, against about
18 s with no queue). Ten times today's volume is far over every cap. Money is not the problem (single dollars a month).

*Evidence:* `cost_and_10x.md`; the 429 body quoted there; seam 44.
*What I would do next:* move off the free tier. The in-code calls are done and measured (25% fewer tokens on 10 tickets, 7 against 8
passing, so equal quality is not shown); a one-call design would cut further but gives up the model's own tool use.

## Also on the list

- **The defences have not been needed yet.** With the version filter and policy guard switched off, 0 of 10 refund answers cited the wrong policy, the same as with them on, even though the unfiltered search showed the model the wrong version in 11 of 39 cases. The guard is insurance; this sample (n = 10) cannot show it is worth its cost.
- **Model output contains invisible and lookalike characters** (zero-width spaces, non-breaking hyphens and spaces) in 24 of 39 replies. They defeat exact-match checks; one blocked a correct answer before the normaliser was added. Any new guard that matches text must normalise first.
- **PII redaction is pattern and list based.** A first name alone, a misspelt name, an unusual address format or a number written in words would pass. Raw prompts and answers sit in the local LLM cache unless `LLM_CACHE=off`.
- **The cheaper path is not proven as good.** Prefetching the entitlement check and first search saved a quarter of the tokens,
  but on the same 10 tickets one more case escalated than without it. n = 10, one run each: it needs a repeated, larger A/B.
- **Docker and CI have never run.** The files are hardened and validated, but no image has been built and no CI runner has executed the workflow.
- **Everything is single-turn, synthetic and templated.** Real re-open behaviour, real help-centre language and account-data errors are not measured.

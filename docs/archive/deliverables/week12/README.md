# Week 12 deliverables

All data is SYNTHETIC. Every number below can be regenerated; the command that produces it is in the right-hand column.
Files marked **needs a person** cannot be completed by the author alone.

Dates: the integration work ran from 2026-10-16 to 2026-10-18, and the gaps a requirements check found were closed on
2026-10-19. The dates in these files are the real ones, so they do not fall on the weekdays the brief names (Tuesday
seam list, Wednesday weaknesses, Thursday review).

| Brief item | File | Produced by |
|---|---|---|
| Detailed description of everything built and changed | `../../WEEK12_IMPLEMENTATION_README.md` | by hand, checked against the code |
| One command, README a stranger can follow | `../../README.md` (Tier-1 section), `../../Makefile`, `../../tasks.ps1` | `make up` (or `./tasks.ps1 up`, `python -m tier1 up`) |
| How to use the app, by role | `../../docs/USER_GUIDE.md` (also in the app under Help) | by hand, checked in a browser |
| Seam list, as hit, each with a status | `seams.md` | written while working; statuses were set at the end |
| One-page architecture | `architecture.md` | by hand, with measured figures in brackets |
| Architecture diagram (SVG and Mermaid) and the database entity diagram | `diagrams/` | by hand; the entity diagram was checked against the real schema |
| Eval report with stated non-coverage, per-mode pass rate, n | `eval/report_fix1.md` (current system); `eval/report_after.md` (before the fixes) | `python -m tier1 eval --tag fix1` |
| Re-scored taxonomy, with the integration-created mode | `taxonomy.md` (run `fix1`, with the change from `after`) | `python scripts/taxonomy_tally.py after fix1` plus reading the traces |
| Trajectory eval and the outcome-vs-trajectory gap | the "Trajectory" section of every `eval/report_*.md`; `eval/report_traj_off.md` is the run where the model makes every tool call itself (prefetch off, 20 cases) | same command; `python -m tier1 eval --tag traj_off --limit 20 --ablate prefetch --no-judge` |
| One end-to-end trace, cost and latency per span, one id across the agent and MCP hops | `trace.json` (RAN16 from `fix1`: a refund answer citing the policy version, uncached model calls, a rate-limiter wait and a refused third search) and `trace_escalate.json` (MIS01 from `fix1`: escalation through the MCP `escalate` tool). No customer email or address appears in either, or in any of the 2,997 stored spans (checked against every customer record on 2026-10-18; orders hold no address) | `python scripts/export_trace.py <trace_id> --out trace.json` (re-exported 2026-10-19: every span now carries a cost, 0.0 for spans that make no model call, and a rolled-up `cost_usd_total`) |
| Judge agreement against hand labels (Week 6 v1 rubric re-checked as the primary judge, plus two second opinions) | **needs a person**: label 20+ replies of `fix1` on the admin page `/label`; the report says "NOT MEASURED" until then. `fix1` was re-graded with v1 on 2026-10-19 (`seams.md` 73) | `python -m tier1 eval --rejudge fix1` (done), then `python -m tier1 eval --rescore fix1` after labelling |
| Top 3 weaknesses, written before anyone asked | `weaknesses.md` (a draft; adopt it and keep your own date) | by hand from the evidence |
| Cost per deflected ticket and the 10x plan | `cost_and_10x.md` (from `fix1`, prices checked 2026-10-18; latency from the uncached run `latency10`) | `python scripts/cost_and_10x.py` |
| Uncached latency | `eval/report_latency10.md` (10 cases, response cache off) | `LLM_CACHE=off python -m tier1 eval --tag latency10 --limit 10 --no-judge` |
| Token cut A/B (prefetch on and off, same 10 tickets) | `eval/report_pf10_on.md`, `eval/report_pf10_off.md` | `python -m tier1 eval --tag pf10_on --limit 10 --no-judge` (add `--ablate prefetch`) |
| Closed failure-to-test loop | `closed_loop.md` (held-out A/B, the production-model re-run, and the live rehearsal in section 7), and Review inbox, Run this test in the UI | `python scripts/closed_loop_report.py holdout_20b_base holdout_20b_fixed`; live steps in `demo_script.md` Part 3 |
| Before and after on a named metric | `eval/report_before.md` against `eval/report_after.md` (version filter and guard off or on); `closed_loop.md` and `eval/report_holdout_20b_*.md` for the source-citation fix | `python -m tier1 eval --tag before --ablate version_filter,policy_guard` |
| Bonus: deflection and simulated re-open together, with a human-reply control | `eval/second_contact.json` (the first, flawed version is kept as `second_contact_v1_gap_forced_by_prompt.json`) | `python -m evaluation.integrated.second_contact` |
| Retrieval baseline | `baseline/README.md`, `baseline/retrieval_baseline.json` | `python scripts/measure_retrieval.py` |
| Fresh-eyes note from another squad | **needs a person**: `fresh_eyes.md` is a template; the server can now be reached over HTTP (`make mcp-http`) | `../../docs/MCP_CLIENT_GUIDE.md` |
| 10-minute demo script and the hostile questions | `demo_script.md` | by hand, numbers from the files above |

## Files in `eval/`

- `results_<tag>.jsonl`: one row per case (checks, trace id, cost, latency, judge verdict, the reply).
- `summary_<tag>.json`: every number the report prints.
- `report_<tag>.md`: the readable report.
- `*_after_run1_judge_without_order_facts.*`: the first full run, kept on purpose. Its judge was missing the order record (seam 31) and one case was over-strict (seam 32); the history stays visible.
- `label_sheet.md`: replies for a human to label. It hides the judge's verdict and the assertion results so they cannot anchor the labeler.
- `second_contact.json`: the follow-up eval.

## Tags used

| Tag | System | Cases |
|---|---|---|
| `after_run1_...` | full system, first run (judge without order facts) | 39 |
| `after` | full system as of the first complete runs (judge fixed, INJ02 criterion corrected), BEFORE the two source fixes. Reproduce today with `--ablate macro_filter,error_code_prompt` | 39 |
| `before` | version filter and policy guard OFF | 39 |
| `holdout_20b_base` | two fixes OFF (macros searchable, no error-code instruction), agent `gpt-oss-20b`, on 15 tickets the fixes were not derived from | 15 |
| `holdout_20b_fixed` | two fixes ON, same model, same 15 tickets | 15 |
| `fix1` | full system TODAY on the production model: both source fixes, prefetch, three judges (Week 6 v1 primary since the 2026-10-19 rejudge; Week 6 v2 and the integrated rubric as second opinions). The current report | 39 |
| `traj_off` | full system with prefetch OFF, so the model makes every tool call itself; no judge (trajectory) | 20 |
| `latency10` | full system, response cache OFF, no judge (latency) | 10 |
| `live_red_*`, `live_green_*` | the live loop rehearsal: one case with the two source fixes off, then on, cache off | 1 each |
| `pf10_on`, `pf10_off` | the first 10 main cases with prefetch on and off, no judge (token cut A/B) | 10 |

The first full re-run of the fixed system (2026-10-16) did not complete: the provider's daily token cap was reached after 6 cases, so it was discarded (seams 44 and 46). The `fix1` files now in `eval/` are a later, complete run (2026-10-18), made possible by the token cut and resumable runs (seam 54).

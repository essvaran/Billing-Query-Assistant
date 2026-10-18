"""Bonus: deflection is a vanity metric on its own. For 10 tickets the system deflected, simulate the customer's
next message and score whether the first answer already pre-empted it.

    python -m evaluation.integrated.second_contact

Reports deflection rate AND simulated re-open rate as a pair, with a control.

Design notes, because a first version of this was wrong:
  * Version 1 told the simulated customer to "ask about the thing the reply left unclear", which produces a gap by
    construction: 10 of 10 follow-ups, 100% re-open. That result is kept as second_contact_v1_gap_forced_by_prompt.json
    and must not be quoted.
  * Version 2 lets the customer say NONE when their problem is solved. A re-open is a follow-up that exists AND was
    not pre-empted by the reply.
  * CONTROL: the same procedure on the original human agent reply to the same ticket (from the resolved-ticket
    set). If the control scores the same, the method cannot tell good replies from bad ones.
Both the follow-up and its grading are written by a model (qwen/qwen3.8-27b, a different family from the agent):
this measures whether replies are complete, not what real customers do. n is small.
"""
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from evaluation.integrated.judge import judge_model
from src.catalog import eval_store, prompts, settings
from src.config import VARIANT_A_DIR
from src.generation import gateway

EVAL_DIR = ROOT / "docs" / "archive" / "deliverables" / "week12" / "eval"
SEED = 1212          # the draw is part of the experiment's definition: change it and the result is a different experiment
# sample size: setting eval.second_contact_sample; prompts: eval.second_contact_followup and eval.second_contact_score

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _ask(system: str, user: str) -> str:
    data = gateway.chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                        model=judge_model(), temperature=0.0)
    return _THINK.sub("", data["choices"][0]["message"].get("content") or "").strip()


def simulate(ticket: str, reply: str) -> dict:
    followup = _ask(prompts.body("eval.second_contact_followup"), f"TICKET:\n{ticket}\n\nREPLY:\n{reply}")
    if followup.upper().strip(" .") == "NONE":
        return {"followup": None, "verdict": "NO_FOLLOWUP", "reason": "customer says it is solved"}
    verdict_text = _ask("You are a strict grader.", prompts.render("eval.second_contact_score", ticket=ticket, reply=reply, followup=followup))
    m = re.search(r"VERDICT:\s*(NOT_PRE_EMPTED|PRE_EMPTED)", verdict_text, re.IGNORECASE)
    reason = (re.search(r"REASON:\s*(.+)", verdict_text) or [None, ""])[1][:240]
    return {"followup": followup, "verdict": m.group(1).upper() if m else "ERROR", "reason": reason}


def rate(rows: list[dict]) -> dict:
    scored = [r for r in rows if r["verdict"] != "ERROR"]
    reopened = sum(r["verdict"] == "NOT_PRE_EMPTED" for r in scored)
    return {"n": len(scored), "reopened": reopened,
            "simulated_reopen_rate": round(reopened / len(scored), 3) if scored else None,
            "no_followup": sum(r["verdict"] == "NO_FOLLOWUP" for r in scored),
            "followup_but_pre_empted": sum(r["verdict"] == "PRE_EMPTED" for r in scored)}


def main(tag: str = "after") -> int:
    rows = eval_store.results(tag)
    cases = {c["case_id"]: c for c in eval_store.cases("main", include_inactive=True)}
    rows = [r for r in rows if r["case_id"] in cases]
    human = {json.loads(l)["ticket_id"]: json.loads(l)["agent_reply"] for l in
             (VARIANT_A_DIR / "tickets_300.jsonl").read_text(encoding="utf-8").splitlines() if l}
    answerable = [r for r in rows if cases[r["case_id"]]["expected_decision"] == "ANSWER"]
    deflected = [r for r in answerable if r["decision"] == "ANSWER" and r["passed"]]
    pick = random.Random(SEED).sample(deflected, min(settings.get("eval.second_contact_sample"), len(deflected)))

    assistant, control = [], []
    for r in pick:
        case = cases[r["case_id"]]
        ticket = f"{case['subject']}\n{case['body']}"
        a = {"case_id": r["case_id"], **simulate(ticket, r["reply"])}
        assistant.append(a)
        line = f"{r['case_id']:<6} assistant: {a['verdict']:<15}"
        if case.get("ticket_id") and case["ticket_id"] in human:       # control: the original human reply, same ticket
            c = {"case_id": r["case_id"], "human_reply": human[case["ticket_id"]], **simulate(ticket, human[case["ticket_id"]])}
            control.append(c)
            line += f" human control: {c['verdict']}"
        print(line, flush=True)

    result = {
        "version": 2,
        "deflection_rate": round(len(deflected) / len(answerable), 3) if answerable else None,
        "deflected": len(deflected), "answerable_cases": len(answerable),
        "assistant": rate(assistant), "human_reply_control": rate(control), "model": judge_model(), "source_run": tag,
        # kept at top level because the insights page reads these two
        "n": rate(assistant)["n"], "simulated_reopen_rate": rate(assistant)["simulated_reopen_rate"],
        "caveat": ("Follow-ups are written and graded by a model, not real customers; n is small. The human control replies are "
                   "short synthetic templates, so a similar re-open rate means the method cannot separate good from poor replies."),
        "rows": assistant, "control_rows": control,
    }
    eval_store.save_run("second_contact", "second_contact", "complete", result, {"source_run": tag}, [])
    (EVAL_DIR / "second_contact.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    a, c = result["assistant"], result["human_reply_control"]
    print(f"\ndeflection {result['deflection_rate']} ({len(deflected)} of {len(answerable)} answerable) | simulated re-open "
          f"{a['simulated_reopen_rate']} ({a['reopened']}/{a['n']}; {a['no_followup']} said solved) | human-reply control "
          f"{c['simulated_reopen_rate']} ({c['reopened']}/{c['n']})")
    return 0


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:2] or ["after"])))

"""The eval runner's arithmetic: slices, superseded rate, trajectory gap, failure modes, agreement."""
import json

import pytest

from evaluation.integrated import run


def case(cid, slice_="random", decision="ANSWER", version="none", tools=(), **kw):
    return {"case_id": cid, "slice": slice_, "expected_decision": decision, "expected_policy_version": version,
            "expected_tools": list(tools), "pair_id": kw.pop("pair_id", ""), **kw}


def row(cid, passed=True, slice_="random", decision="ANSWER", version="none", failed=(), violations=(), tokens=1000,
        judge=None, pair_id="", checks=None, cost=0.001, expected="ANSWER"):
    return {"case_id": cid, "slice": slice_, "pair_id": pair_id, "expected_decision": expected,
            "expected_policy_version": version, "decision": decision, "reason": "", "passed": passed,
            "checks": checks or {}, "failed_checks": [{"name": n, "detail": ""} for n in failed],
            "tools_called": [], "citations": [], "violations": list(violations), "trace_id": f"t-{cid}",
            "latency_ms": 2000.0, "total_tokens": tokens, "cost_usd": cost, "laps": 3, "reply": "x",
            "draft": "", "entitlement": None, "sources": [], "judge": judge}


def summary(cases, rows):
    return run.summarise(cases, rows, "t", "")


def test_slice_pass_rates_and_overall():
    cases = [case("a"), case("b"), case("c", "shipping")]
    rows = [row("a"), row("b", passed=False, failed=["cites_gold_source"], checks={"cites_gold_source": False}),
            row("c", slice_="shipping")]
    s = summary(cases, rows)
    assert s["n"] == 3 and s["passed"] == 2
    assert s["by_slice"]["random"] == {"passed": 1, "n": 2, "rate": 0.5}


def test_both_versions_reports_pairs_not_just_the_average():
    cases = [case(f"p{i}", "both_versions", version=v, pair_id=pid)
             for i, (v, pid) in enumerate([("refund-14d", "pair1"), ("refund-30d", "pair1"),
                                           ("refund-14d", "pair2"), ("refund-30d", "pair2")])]
    rows = [row("p0", slice_="both_versions", version="refund-14d", pair_id="pair1"),
            row("p1", slice_="both_versions", version="refund-30d", pair_id="pair1"),
            row("p2", slice_="both_versions", version="refund-14d", pair_id="pair2", passed=False,
                failed=["names_policy_version"], checks={"names_policy_version": False}),
            row("p3", slice_="both_versions", version="refund-30d", pair_id="pair2")]
    bv = summary(cases, rows)["both_versions"]
    assert bv["pairs_both_correct"] == 1 and bv["pairs"] == 2
    assert bv["legacy_14d"] == {"n": 2, "passed": 1} and bv["current_30d"] == {"n": 2, "passed": 2}


def test_superseded_rate_counts_shown_and_blocked_separately():
    cases = [case(f"r{i}", version="refund-30d") for i in range(4)]
    rows = [row("r0", version="refund-30d"),
            row("r1", version="refund-30d", passed=False, failed=["no_superseded_citation"],
                checks={"no_superseded_citation": False}),
            row("r2", version="refund-30d", decision="ESCALATE", passed=False, violations=["superseded_policy"],
                failed=["decision_matches"]),
            row("r3", version="refund-30d")]
    sp = summary(cases, rows)["superseded_policy"]
    assert sp["final_answers_citing_wrong_version"] == 1 and sp["answered"] == 3
    assert sp["drafts_blocked_by_guard"] == 1
    assert sp["attempted_rate"] == pytest.approx(0.5)


def test_trajectory_gap_separates_lucky_answers_from_correct_paths():
    cases = [case(f"t{i}", tools=["check_entitlement"]) for i in range(4)]
    ok = {"decision_matches": True, "expected_tools_called": True}
    lucky = {"decision_matches": True, "expected_tools_called": False}      # right answer, wrong path
    wrong_answer = {"decision_matches": False, "expected_tools_called": True}
    rows = [row("t0", checks=ok), row("t1", checks=ok), row("t2", checks=lucky), row("t3", checks=wrong_answer)]
    tj = summary(cases, rows)["trajectory"]
    assert tj["n"] == 4 and tj["right_answer_wrong_path"] == 1 and tj["right_path_wrong_answer"] == 1
    assert tj["tool_choice_accuracy"] == 0.75 and tj["outcome_accuracy"] == 0.75 and tj["gap_points"] == 0.0


def test_failure_modes_are_named_by_priority():
    c_answer = case("x", version="refund-30d", tools=["check_entitlement"])
    c_escal = case("y", decision="ESCALATE")
    assert run.mode_of(c_answer, row("x", failed=["no_superseded_citation", "eligibility_consistent"]))[0] == "wrong_policy_version"
    assert run.mode_of(c_answer, row("x", failed=["decision_matches"]))[0] == "over_escalation"
    assert run.mode_of(c_escal, row("y", failed=["decision_matches"]))[0] == "unsafe_answer_when_must_escalate"
    assert run.mode_of(c_answer, row("x", failed=["expected_tools_called"]))[0] == "entitlement_not_checked"
    assert run.mode_of(c_answer, row("x", failed=["no_pii_in_reply"]))[1] == "critical"


def test_cost_per_deflected_ticket_divides_all_spend_by_deflected_only():
    cases = [case(f"c{i}") for i in range(4)]
    rows = [row("c0", cost=0.001), row("c1", cost=0.001),
            row("c2", decision="ESCALATE", passed=False, failed=["decision_matches"], cost=0.001),
            row("c3", tokens=0, cost=0.0)]
    cl = summary(cases, rows)["cost_latency"]
    assert cl["deflected_assertions_only"] == 3                       # c0, c1, c3 answered and passed
    assert cl["cost_per_deflected_usd"] == pytest.approx(0.003 / 3)
    assert cl["tickets_with_no_model_call"] == 1


def _judged(cid, verdict):
    return row(cid, judge={"verdict": verdict, "model": "m", "reason": ""})


def test_agreement_is_unmeasured_without_labels():
    assert run.agreement([_judged("a", "GOOD")])["n"] == 0


def test_agreement_counts_only_labelled_and_judged_and_flags_the_dangerous_error():
    from src.catalog import eval_store
    eval_store.set_labeler("J", "2y Tier-1", "test")
    for cid, label in (("a", "GOOD"), ("b", "NOT_GOOD"), ("c", "NOT_GOOD")):
        eval_store.set_label(cid, "x", label, "t", "test")          # row() replies are "x"
    ag = run.agreement([_judged("a", "GOOD"), _judged("b", "GOOD"), _judged("c", "NOT_GOOD"), _judged("d", "GOOD")])
    assert ag["n"] == 3 and ag["agree"] == 2
    assert ag["judge_good_human_not_good"] == 1       # the judge approved what the human rejected
    assert ag["meets_target"] is False                # n is below the minimum label count, so no pass


def test_report_refuses_to_quote_agreement_when_unmeasured():
    cases, rows = [case("a")], [_judged("a", "GOOD")]
    text = run.render_report(summary(cases, rows), rows)
    assert "NOT MEASURED" in text and "What this suite does NOT cover" in text

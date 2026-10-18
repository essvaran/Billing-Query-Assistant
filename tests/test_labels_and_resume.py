"""Human labels are tied to the reply they were given for; resume and rescore never spend model calls twice.
Everything here reads and writes the catalog database (a fresh copy per test, see conftest.py)."""
import json

import pytest

from evaluation.integrated import labels, run
from src.catalog import eval_store


def _row(cid, reply="Reply text.", verdict="GOOD", alt=None, **kw):
    return {"case_id": cid, "reply": reply, "judge": {"verdict": verdict, "model": "m", "version": "week6-v2r"},
            "judge_alt": {"verdict": alt, "model": "m", "version": "v3b"} if alt else None, **kw}


def test_label_counts_only_for_the_reply_it_was_given_for():
    labels.set_label("A", "Old reply.", "GOOD", tag="after")
    assert labels.agreement([_row("A", reply="Old reply.")])["n"] == 1
    # a later run answered the same case differently: the old label must not grade the new reply
    assert labels.agreement([_row("A", reply="A different reply.")])["n"] == 0


def test_whitespace_changes_do_not_orphan_a_label():
    labels.set_label("A", "Line one.\nLine two.", "NOT_GOOD", tag="t")
    assert labels.label_for(_row("A", reply="Line one.  Line two."), labels.load()) == "NOT_GOOD"


def test_skip_removes_a_label_and_bad_values_are_refused():
    labels.set_label("A", "r", "GOOD", tag="t")
    labels.set_label("A", "r", None, tag="t")
    assert "A" not in labels.load()["labels"]
    with pytest.raises(ValueError):
        labels.set_label("A", "r", "MAYBE", tag="t")


def test_labeler_is_stored_with_the_labels():
    labels.set_labeler("Sam Lee", "2 years Tier-1")
    data = labels.load()
    assert data["labeler"] == "Sam Lee" and data["queue_experience"] == "2 years Tier-1"


def test_agreement_is_reported_per_judge():
    rows = [_row(f"R{i}x", reply=f"r{i}", verdict="GOOD", alt="NOT_GOOD") for i in range(3)]
    for i in range(3):
        labels.set_label(f"R{i}x", f"r{i}", "GOOD", tag="t")
    assert labels.agreement(rows, "judge")["agreement"] == 1.0
    assert labels.agreement(rows, "judge_alt")["agreement"] == 0.0
    assert labels.agreement(rows, "judge")["meets_target"] is False      # n=3 is below the minimum


def test_target_and_minimum_come_from_settings():
    from src.catalog import settings
    settings.set("eval.min_labels", 2, "test")
    settings.set("eval.agreement_target", 0.5, "test")
    rows = [_row(f"S{i}", reply=f"r{i}") for i in range(2)]
    for i in range(2):
        labels.set_label(f"S{i}", f"r{i}", "GOOD", tag="t")
    ag = labels.agreement(rows)
    assert ag["meets_target"] is True and ag["target"] == 0.5 and ag["min_labels"] == 2


def _saved_row(case):
    return {"case_id": case["case_id"], "slice": case["slice"], "pair_id": case["pair_id"],
            "expected_decision": case["expected_decision"], "expected_policy_version": case["expected_policy_version"],
            "decision": "ANSWER", "reason": "", "passed": True, "checks": {}, "failed_checks": [], "tools_called": [],
            "citations": [], "violations": [], "trace_id": "t", "latency_ms": 1.0, "total_tokens": 10, "cost_usd": 0.0,
            "laps": 1, "reply": "hello", "draft": "", "entitlement": None, "sources": [],
            "judge": {"verdict": "GOOD", "model": "m", "version": "week6-v2r"}, "judge_alt": None}


def test_rescore_recomputes_from_saved_rows_without_model_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "OUT_DIR", tmp_path)
    case = eval_store.cases("main")[0]
    eval_store.save_run("x", "main", "complete", {"ablate": None, "llm_cache": {"hits": 1, "misses": 0}}, {}, [_saved_row(case)])
    labels.set_label(case["case_id"], "hello", "GOOD", tag="x")

    def boom(*a, **k):
        raise AssertionError("rescore must not call the model")
    monkeypatch.setattr(run, "run_cases", boom)

    assert run.main(["--rescore", "x"]) == 0
    s = eval_store.run("x")["summary"]
    assert s["rescored"] is True and s["llm_cache"] == {"hits": 1, "misses": 0}
    assert s["judge"]["agreement"]["n"] == 1
    assert "Agreement with human labels: **1/1" in (tmp_path / "report_x.md").read_text(encoding="utf-8")


def test_resume_skips_finished_cases_and_refuses_different_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "OUT_DIR", tmp_path)
    cases = run.load_cases(None, 2)
    meta = {"ablate": "", "cases": "main", "only": None, "limit": 2, "case_id": None, "judge": False}
    eval_store.save_run("r", "main", "partial", {}, meta, [{"case_id": cases[0]["case_id"]}])

    assert run.main(["--tag", "r", "--limit", "2", "--resume"]) == 2              # judge on vs off: refused

    seen = {}

    def fake_run(cs, judge, done=None):
        seen["done"] = [d["case_id"] for d in done]
        raise run.RateLimitAbort(done, cs[1]["case_id"], "cap")
    monkeypatch.setattr(run, "run_cases", fake_run)
    assert run.main(["--tag", "r", "--limit", "2", "--no-judge", "--resume"]) == 3
    assert seen["done"] == [cases[0]["case_id"]]
    assert eval_store.run("r")["status"] == "partial"                             # kept for the next resume


def test_regression_source_reads_only_regression_cases():
    base = {k: v for k, v in eval_store.cases("main")[0].items() if k not in ("case_id",)}
    for cid in ("REG01", "REG02"):
        eval_store.save_case(cid, "regression", {**base, "slice": "regression"}, "test", create=True)
    assert [c["case_id"] for c in run.load_cases(None, None, "regression")] == ["REG01", "REG02"]
    assert [c["case_id"] for c in run.load_cases(None, None, "regression", ["REG02"])] == ["REG02"]


def test_seed_imported_the_old_files():
    assert len(eval_store.cases("main")) == 39 and len(eval_store.cases("holdout")) == 15
    week6 = eval_store.run("week6")
    assert week6 and week6["summary"]["n"] == 26        # 25 Week 6 cases plus G07, added later and never labelled
    from evaluation.integrated.judge import week6_human_agreement
    # computed from the stored labels, not typed in: v2 agreed on 20 of 25, v1 on 24 of 25 (the old "both 96%" was wrong)
    assert week6_human_agreement() == "v2 20/25 = 80%; v1 24/25 = 96% (Week 6 labels)"

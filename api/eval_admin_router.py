"""Admin API for evaluation data in the catalog: cases (create, edit, switch off, delete), runs and per-case results.

The Week 6 page and the Insights page read their numbers from here instead of from values typed into the frontend.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import UserOut, require_admin
from src.catalog import eval_store

router = APIRouter(prefix="/api/admin/eval", tags=["eval-admin"])


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(400, str(exc))


class CaseIn(BaseModel):
    case_id: str | None = Field(None, max_length=40)
    suite: str = Field(pattern="^(main|holdout|regression|docs)$")
    data: dict[str, Any]


class ActiveIn(BaseModel):
    active: bool


class NotesIn(BaseModel):
    notes: str = Field("", max_length=20000)


@router.get("/cases")
def list_cases(suite: str = Query("", pattern="^(|main|holdout|regression|docs)$"), include_inactive: bool = True,
               _admin: UserOut = Depends(require_admin)):
    return eval_store.cases(suite or None, include_inactive=include_inactive)


@router.get("/cases/{case_id}")
def get_case(case_id: str, _admin: UserOut = Depends(require_admin)):
    case = eval_store.get_case(case_id)
    if case is None:
        raise HTTPException(404, f"No case {case_id}")
    return case


@router.post("/cases", status_code=201)
def create_case(body: CaseIn, admin: UserOut = Depends(require_admin)):
    case_id = body.case_id or eval_store.next_case_id({"regression": "REG", "docs": "PF"}.get(body.suite, "CASE"))
    try:
        return eval_store.save_case(case_id, body.suite, body.data, admin.email, create=True)
    except eval_store.EvalStoreError as exc:
        raise _bad(exc)


@router.put("/cases/{case_id}")
def update_case(case_id: str, body: CaseIn, admin: UserOut = Depends(require_admin)):
    try:
        return eval_store.save_case(case_id, body.suite, body.data, admin.email, create=False)
    except eval_store.EvalStoreError as exc:
        raise _bad(exc)


@router.post("/cases/{case_id}/active")
def set_active(case_id: str, body: ActiveIn, admin: UserOut = Depends(require_admin)):
    try:
        return eval_store.set_case_active(case_id, body.active, admin.email)
    except eval_store.EvalStoreError as exc:
        raise _bad(exc)


@router.delete("/cases/{case_id}", status_code=204)
def delete_case(case_id: str, admin: UserOut = Depends(require_admin)):
    try:
        eval_store.delete_case(case_id, admin.email)
    except eval_store.EvalStoreError as exc:
        raise _bad(exc)


@router.get("/runs")
def list_runs(suite: str = Query("", max_length=30), _admin: UserOut = Depends(require_admin)):
    return [{k: r[k] for k in ("tag", "suite", "status", "notes", "created_at", "updated_at", "n_rows")}
            | {"n": (r["summary"] or {}).get("n"), "passed": (r["summary"] or {}).get("passed"),
               "pass_rate": (r["summary"] or {}).get("pass_rate")}
            for r in eval_store.runs(suite or None)]


@router.get("/runs/{tag}")
def get_run(tag: str, _admin: UserOut = Depends(require_admin)):
    run = eval_store.run(tag)
    if run is None:
        raise HTTPException(404, f"No run {tag}")
    return {**run, "results": eval_store.results(tag)}


@router.put("/runs/{tag}/notes")
def update_notes(tag: str, body: NotesIn, admin: UserOut = Depends(require_admin)):
    try:
        return eval_store.update_run_notes(tag, body.notes, admin.email)
    except eval_store.EvalStoreError as exc:
        raise _bad(exc)


@router.delete("/runs/{tag}", status_code=204)
def delete_run(tag: str, admin: UserOut = Depends(require_admin)):
    try:
        eval_store.delete_run(tag, admin.email)
    except eval_store.EvalStoreError as exc:
        raise _bad(exc)


@router.get("/week6")
def week6(_admin: UserOut = Depends(require_admin)):
    """Everything the Week 6 page shows, computed from the stored Week 6 run and its labels."""
    from collections import Counter
    from evaluation.integrated import labels
    from src.catalog import prompts, ref
    run = eval_store.run("week6")
    if run is None:
        raise HTTPException(404, "The Week 6 run is not stored")
    rows = eval_store.results("week6")
    human = labels.load()
    for r in rows:
        r["human_label"] = labels.label_for(r, human)
    modes = ref.values("week6_failure_mode", include_inactive=True)
    checks = sorted({k for r in rows for k in (r.get("checks") or {})})
    by_mode = []
    for m in modes:
        sub = [r for r in rows if r.get("mode") == m["code"]]
        by_mode.append({"mode": m["code"], "label": m["label"], "short": m["meta"].get("short", m["code"]),
                        "description": m["description"], "n": len(sub),
                        "checks": {c: sum(1 for r in sub if (r.get("checks") or {}).get(c)) for c in checks},
                        "judge_good": {k: sum(1 for r in sub if (r.get(k) or {}).get("verdict") == "GOOD") for k in ("judge", "judge_alt")}})
    judges = {}
    for key in ("judge", "judge_alt"):
        verdicts = Counter((r.get(key) or {}).get("verdict") for r in rows if r.get(key))
        judges[key] = {"version": next(((r.get(key) or {}).get("version") for r in rows if r.get(key)), None),
                       "good": verdicts.get("GOOD", 0), "not_good": verdicts.get("NOT_GOOD", 0),
                       "agreement": labels.agreement(rows, key),
                       "disagreements": [r["case_id"] for r in rows if r.get("human_label") and (r.get(key) or {}).get("verdict")
                                         and r["human_label"] != r[key]["verdict"]]}
    return {"run": {k: run[k] for k in ("tag", "notes", "created_at", "updated_at")} | {"summary": run["summary"]},
            "n": len(rows), "labelled": sum(1 for r in rows if r["human_label"]),
            "regressions": [r["case_id"] for r in rows if r.get("is_regression")],
            "checks": checks, "by_mode": by_mode, "judges": judges, "rows": rows,
            "prompts": {"week6-v2": prompts.body("judge.week6_v2"), "week6-v1": prompts.body("judge.week6_v1")}}

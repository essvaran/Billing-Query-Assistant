"""Evaluation data in the catalog: cases, runs, per-case results and human labels.

Suites
  main, holdout, regression   Tier-1 integrated eval (regression = cases created from reported failures)
  docs                        Docs-mode eval set (the Week 6 cases plus cases added from production traces)

The first run imports what used to be files (evaluation/integrated/*.jsonl, labels.json, evaluation/eval_set.jsonl,
the Week 6 answers and labels, and every saved run under docs/archive/deliverables/week12/eval). After that the database is the
source of truth; report files are still written for people to read, but nothing reads them back.
"""
import hashlib
import json
import sqlite3

from src.catalog import db, ref
from src.config import PROJECT_ROOT

TIER1_SUITES = ("main", "holdout", "regression")
SUITES = TIER1_SUITES + ("docs",)
DECISIONS = ("ANSWER", "ESCALATE")
DOCS_EXPECTED = ("answer", "refusal")


class EvalStoreError(ValueError):
    pass


def reply_sha(reply: str) -> str:
    return hashlib.sha256(" ".join((reply or "").split()).encode("utf-8")).hexdigest()[:16]


# --- one-time import of the old files ------------------------------------------------------------------

def _jsonl(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def import_files(conn: sqlite3.Connection) -> None:
    integ = PROJECT_ROOT / "evaluation" / "integrated"
    for suite, path in (("main", integ / "cases.jsonl"), ("holdout", integ / "cases_holdout.jsonl"),
                        ("regression", integ / "regression_cases.jsonl"),
                        ("docs", PROJECT_ROOT / "evaluation" / "eval_set.jsonl")):
        for i, case in enumerate(_jsonl(path)):
            conn.execute("INSERT OR IGNORE INTO eval_cases(case_id, suite, slice, data, position, source) VALUES (?,?,?,?,?,?)",
                         (case["case_id"], suite, case.get("slice") or case.get("mode") or "", json.dumps(case), i, path.name))

    out = PROJECT_ROOT / "docs" / "archive" / "deliverables" / "week12" / "eval"
    for summary_path in sorted(out.glob("summary_*.json")) if out.exists() else []:
        tag = summary_path.stem[len("summary_"):]
        rows = _jsonl(out / f"results_{tag}.jsonl")
        if not rows:
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        settings = summary.get("settings") or {}
        suite = settings.get("cases") or ("holdout" if tag.startswith("holdout") else "main")
        _insert_run(conn, tag, suite, "complete", summary, settings, rows, at=_mtime(summary_path))
    for partial in sorted(out.glob("results_*_PARTIAL.jsonl")) if out.exists() else []:
        tag = partial.stem[len("results_"):-len("_PARTIAL")]
        _insert_run(conn, tag, "main", "partial", {}, {}, _jsonl(partial))
    for name in ("second_contact", "second_contact_v1_gap_forced_by_prompt"):
        path = out / f"{name}.json"
        if path.exists():
            _insert_run(conn, name, "second_contact", "complete", json.loads(path.read_text(encoding="utf-8")), {}, [])

    labels_file = integ / "labels.json"
    if labels_file.exists():
        data = json.loads(labels_file.read_text(encoding="utf-8"))
        for cid, v in (data.get("labels") or {}).items():
            if isinstance(v, dict) and v.get("label") in ("GOOD", "NOT_GOOD"):
                conn.execute("INSERT OR IGNORE INTO eval_labels(case_id, label, reply_sha, tag, labeler, at) VALUES (?,?,?,?,?,?)",
                             (cid, v["label"], v.get("reply_sha"), v.get("tag", ""), data.get("labeler", ""), v.get("at") or ""))
        if data.get("labeler"):
            conn.execute("INSERT OR REPLACE INTO catalog_meta(key, value) VALUES ('labeler', ?)",
                         (json.dumps({"name": data.get("labeler", ""), "queue_experience": data.get("queue_experience", "")}),))
    _import_week6(conn)


def _import_week6(conn: sqlite3.Connection) -> None:
    ev = PROJECT_ROOT / "evaluation"
    answers = [r for r in _jsonl(ev / "answers_25.jsonl") if r.get("case_id")]
    if not answers:
        return
    v1 = {r["case_id"]: r["label"] for r in json.loads((ev / "prediction_v1.json").read_text(encoding="utf-8"))} \
        if (ev / "prediction_v1.json").exists() else {}
    humans = {r["case_id"]: r for r in json.loads((ev / "labels_25.json").read_text(encoding="utf-8"))} \
        if (ev / "labels_25.json").exists() else {}
    docs_cases = {json.loads(r[0])["case_id"]: json.loads(r[0]) for r in conn.execute("SELECT data FROM eval_cases WHERE suite='docs'")}
    rows = []
    for r in answers:
        case = docs_cases.get(r["case_id"], {})
        rows.append({
            "case_id": r["case_id"], "question": r["question"], "mode": r["mode"], "expected_behavior": r["expected_behavior"],
            "is_regression": bool(r.get("is_regression")), "regression_trace_id": case.get("regression_trace_id"),
            "reply": r.get("final_answer", ""), "citations_valid": r.get("citations_valid"),
            "retrieved_chunk_ids": r.get("retrieved_chunk_ids", []),
            "checks": {k: v.get("passed") for k, v in (r.get("assertions") or {}).items()},
            "check_details": {k: v.get("detail") for k, v in (r.get("assertions") or {}).items()},
            "passed": bool(r.get("all_assertions_pass")),
            "judge": {"verdict": r.get("judge_v2"), "version": "week6-v2"} if r.get("judge_v2") else None,
            "judge_alt": {"verdict": v1[r["case_id"]], "version": "week6-v1"} if r["case_id"] in v1 else None,
        })
        h = humans.get(r["case_id"])
        if h and h.get("label") in ("GOOD", "NOT_GOOD"):
            conn.execute("INSERT OR IGNORE INTO eval_labels(case_id, label, reply_sha, tag, labeler, at) VALUES (?,?,?,?,?,?)",
                         (r["case_id"], h["label"], reply_sha(r.get("final_answer", "")), "week6", "Week 6 labeler", ""))
    summary = {"tag": "week6", "n": len(rows), "passed": sum(r["passed"] for r in rows),
               "model": "openai/gpt-oss-120b", "run_date": "2026-09-03",
               "notes_source": "evaluation/answers_25.jsonl, prediction_v1.json, labels_25.json"}
    _insert_run(conn, "week6", "docs", "complete", summary, {}, rows,
                notes="Week 6 eval of the Docs pipeline: 25 cases, 4 failure modes, deterministic assertions first, then two judge "
                      "rubrics compared with human labels. Imported from the Week 6 result files.")


def _mtime(path) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _insert_run(conn, tag, suite, status, summary, settings, rows, notes="", at=None):
    conn.execute("INSERT OR REPLACE INTO eval_runs(tag, suite, status, summary, settings, notes, created_at, updated_at) "
                 "VALUES (?,?,?,?,?,?,COALESCE(?, datetime('now')),COALESCE(?, datetime('now')))",
                 (tag, suite, status, json.dumps(summary), json.dumps(settings), notes, at, at))
    conn.execute("DELETE FROM eval_results WHERE tag=?", (tag,))
    for i, row in enumerate(rows):
        conn.execute("INSERT OR REPLACE INTO eval_results(tag, case_id, position, row) VALUES (?,?,?,?)",
                     (tag, row["case_id"], i, json.dumps(row)))


# --- cases --------------------------------------------------------------------------------------------

def cases(suite: str | None = None, include_inactive: bool = False) -> list[dict]:
    with db.connect() as conn:
        q = "SELECT * FROM eval_cases WHERE 1=1" + (" AND suite=?" if suite else "") + ("" if include_inactive else " AND active=1")
        rows = conn.execute(q + " ORDER BY suite, position, case_id", (suite,) if suite else ()).fetchall()
    return [_case_out(r) for r in rows]


def _case_out(r) -> dict:
    return {**json.loads(r["data"]), "case_id": r["case_id"], "suite": r["suite"], "active": bool(r["active"]),
            "source": r["source"], "updated_at": r["updated_at"], "updated_by": r["updated_by"]}


def get_case(case_id: str) -> dict | None:
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM eval_cases WHERE case_id=?", (case_id,)).fetchone()
    return _case_out(r) if r else None


def validate_case(suite: str, data: dict) -> dict:
    if suite not in SUITES:
        raise EvalStoreError(f"suite must be one of {list(SUITES)}")
    d = dict(data)
    for k in ("case_id", "suite", "active", "source", "updated_at", "updated_by"):
        d.pop(k, None)
    if suite == "docs":
        for key in ("question",):
            if not str(d.get(key) or "").strip():
                raise EvalStoreError(f"{key} is required")
        if d.get("mode") not in ref.codes("week6_failure_mode"):
            raise EvalStoreError(f"mode must be one of {ref.codes('week6_failure_mode')}")
        if d.get("expected_behavior") not in DOCS_EXPECTED:
            raise EvalStoreError(f"expected_behavior must be one of {list(DOCS_EXPECTED)}")
        d["is_regression"] = bool(d.get("is_regression"))
        return d
    for key in ("body", "slice"):
        if not str(d.get(key) or "").strip():
            raise EvalStoreError(f"{key} is required")
    if d.get("expected_decision") not in DECISIONS:
        raise EvalStoreError(f"expected_decision must be one of {list(DECISIONS)}")
    policies = ref.codes("policy_version")
    if d.get("expected_policy_version", "none") not in policies:
        raise EvalStoreError(f"expected_policy_version must be one of {policies}")
    reasons = set(ref.codes("escalation_reason"))
    for key in ("expected_tools", "forbidden_tools", "accepted_reasons", "accepted_decisions"):
        d[key] = list(d.get(key) or [])
    bad = [r for r in d["accepted_reasons"] if r not in reasons]
    if bad:
        raise EvalStoreError(f"unknown escalation reasons: {bad}")
    tools = set(ref.codes("tier1_tool"))
    bad = [t for t in d["expected_tools"] + d["forbidden_tools"] if t not in tools]
    if bad:
        raise EvalStoreError(f"unknown tools: {bad}")
    for key, default in (("subject", ""), ("customer_id", ""), ("order_id", ""), ("ticket_id", ""), ("gold_slug", ""),
                         ("pair_id", ""), ("notes", ""), ("expected_policy_version", "none")):
        d[key] = str(d.get(key) if d.get(key) is not None else default)
    if d.get("expect_eligible") not in (True, False, None):
        raise EvalStoreError("expect_eligible must be true, false or empty")
    if d.get("expected_days") is not None and not isinstance(d["expected_days"], int):
        raise EvalStoreError("expected_days must be a whole number or empty")
    return d


def save_case(case_id: str, suite: str, data: dict, actor: str, create: bool, source: str = "admin") -> dict:
    case_id = (case_id or "").strip()
    if not case_id or len(case_id) > 40 or not all(c.isalnum() or c in "-_" for c in case_id):
        raise EvalStoreError("case_id must be 1 to 40 letters, digits, dashes or underscores")
    clean = validate_case(suite, data)
    with db.connect() as conn:
        existing = conn.execute("SELECT * FROM eval_cases WHERE case_id=?", (case_id,)).fetchone()
        if create and existing:
            raise EvalStoreError(f"case {case_id} already exists")
        if not create and not existing:
            raise EvalStoreError(f"no case {case_id}")
        if create:
            pos = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM eval_cases WHERE suite=?", (suite,)).fetchone()[0]
            conn.execute("INSERT INTO eval_cases(case_id, suite, slice, data, position, source, updated_by) VALUES (?,?,?,?,?,?,?)",
                         (case_id, suite, clean.get("slice") or clean.get("mode") or "", json.dumps({**clean, "case_id": case_id}),
                          pos, source, actor))
        else:
            conn.execute("UPDATE eval_cases SET suite=?, slice=?, data=?, updated_at=datetime('now'), updated_by=? WHERE case_id=?",
                         (suite, clean.get("slice") or clean.get("mode") or "", json.dumps({**clean, "case_id": case_id}), actor, case_id))
        db.log_change(conn, actor, "eval_case", case_id, "create" if create else "update",
                      json.loads(existing["data"]) if existing else None, clean)
    return get_case(case_id)


def set_case_active(case_id: str, active: bool, actor: str) -> dict:
    with db.connect() as conn:
        if conn.execute("UPDATE eval_cases SET active=?, updated_at=datetime('now'), updated_by=? WHERE case_id=?",
                        (int(active), actor, case_id)).rowcount == 0:
            raise EvalStoreError(f"no case {case_id}")
        db.log_change(conn, actor, "eval_case", case_id, "activate" if active else "deactivate")
    return get_case(case_id)


def delete_case(case_id: str, actor: str) -> None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM eval_cases WHERE case_id=?", (case_id,)).fetchone()
        if row is None:
            raise EvalStoreError(f"no case {case_id}")
        conn.execute("DELETE FROM eval_cases WHERE case_id=?", (case_id,))
        db.log_change(conn, actor, "eval_case", case_id, "delete", json.loads(row["data"]), None)


def next_case_id(prefix: str) -> str:
    with db.connect() as conn:
        used = [r[0][len(prefix):] for r in conn.execute("SELECT case_id FROM eval_cases WHERE case_id LIKE ?", (prefix + "%",))]
    nums = [int(u) for u in used if u.isdigit()]
    return f"{prefix}{(max(nums) + 1 if nums else 1):02d}"


# --- runs and results ---------------------------------------------------------------------------------

def save_run(tag: str, suite: str, status: str, summary: dict, settings: dict, rows: list[dict]) -> None:
    with db.connect() as conn:
        _insert_run(conn, tag, suite, status, summary, settings, rows)
        db.bump(conn)


def runs(suite: str | None = None) -> list[dict]:
    with db.connect() as conn:
        q = "SELECT r.*, (SELECT COUNT(*) FROM eval_results x WHERE x.tag=r.tag) AS n_rows FROM eval_runs r" + \
            (" WHERE suite=?" if suite else "") + " ORDER BY updated_at DESC"
        return [{**dict(r), "summary": json.loads(r["summary"]), "settings": json.loads(r["settings"])}
                for r in conn.execute(q, (suite,) if suite else ())]


def run(tag: str) -> dict | None:
    with db.connect() as conn:
        r = conn.execute("SELECT * FROM eval_runs WHERE tag=?", (tag,)).fetchone()
    return {**dict(r), "summary": json.loads(r["summary"]), "settings": json.loads(r["settings"])} if r else None


def results(tag: str) -> list[dict]:
    with db.connect() as conn:
        return [json.loads(r["row"]) for r in conn.execute("SELECT row FROM eval_results WHERE tag=? ORDER BY position", (tag,))]


def update_run_notes(tag: str, notes: str, actor: str) -> dict:
    with db.connect() as conn:
        if conn.execute("UPDATE eval_runs SET notes=?, updated_at=datetime('now') WHERE tag=?", (notes, tag)).rowcount == 0:
            raise EvalStoreError(f"no run {tag}")
        db.log_change(conn, actor, "eval_run", tag, "notes")
    return run(tag)


def delete_run(tag: str, actor: str) -> None:
    with db.connect() as conn:
        if conn.execute("DELETE FROM eval_runs WHERE tag=?", (tag,)).rowcount == 0:
            raise EvalStoreError(f"no run {tag}")
        db.log_change(conn, actor, "eval_run", tag, "delete")


# --- human labels -------------------------------------------------------------------------------------

def labels() -> dict:
    with db.connect() as conn:
        meta = conn.execute("SELECT value FROM catalog_meta WHERE key='labeler'").fetchone()
        rows = {r["case_id"]: dict(r) for r in conn.execute("SELECT * FROM eval_labels")}
    who = json.loads(meta["value"]) if meta else {}
    return {"labeler": who.get("name", ""), "queue_experience": who.get("queue_experience", ""), "labels": rows}


def set_label(case_id: str, reply: str, label: str | None, tag: str, actor: str) -> None:
    if label is not None and label not in ("GOOD", "NOT_GOOD"):
        raise EvalStoreError("label must be GOOD, NOT_GOOD or empty")
    who = labels()["labeler"] or actor
    with db.connect() as conn:
        if label is None:
            conn.execute("DELETE FROM eval_labels WHERE case_id=?", (case_id,))
        else:
            conn.execute("INSERT OR REPLACE INTO eval_labels(case_id, label, reply_sha, tag, labeler, at) VALUES (?,?,?,?,?,datetime('now'))",
                         (case_id, label, reply_sha(reply), tag, who))
        db.log_change(conn, actor, "eval_label", case_id, "set" if label else "clear", None, label)


def set_labeler(name: str, queue_experience: str, actor: str) -> dict:
    value = {"name": name.strip()[:100], "queue_experience": queue_experience.strip()[:200]}
    with db.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO catalog_meta(key, value) VALUES ('labeler', ?)", (json.dumps(value),))
        db.log_change(conn, actor, "eval_labeler", "labeler", "set", None, value)
    return value

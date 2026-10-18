"""Versioned Tier-1 guard rules and the examples that test them, read from the catalog.

Rules (the regular expressions the pre-guard and post-guard use) change only through a new version that must pass
every stored example before it can go live: each "must catch" example has to be caught by the expected category and
each "must pass" example must not be caught. A rule set that would let a known injection or legal threat through is
therefore refused. Any earlier version can be restored, through the same gate.

Example `expect` values
  pre stage:  a pre-guard category (e.g. prompt_injection), or "pass"
  post stage: a post rule name (claim_topics, refund_topic, money_claim) that must match, or "!name" that must not
"""
import json
import re
import sqlite3

from src.catalog import db

POST_RULES = ("claim_topics", "refund_topic", "money_claim")


class GuardError(ValueError):
    pass


def seed(conn: sqlite3.Connection) -> None:
    data = db.read_json("guards.json")
    if not conn.execute("SELECT 1 FROM guard_rule_sets").fetchone():
        report = gate(data["rules"], [dict(e, id=i) for i, e in enumerate(data["examples"])])
        conn.execute("INSERT INTO guard_rule_sets(version, rules, status, note, test_report, activated_at) "
                     "VALUES (1, ?, 'active', 'seeded from the code', ?, datetime('now'))",
                     (json.dumps(data["rules"]), json.dumps(report)))
    if not conn.execute("SELECT 1 FROM catalog_meta WHERE key='seeded:guard_examples'").fetchone():
        for e in data["examples"]:
            conn.execute("INSERT INTO guard_examples(stage, text, expect, note) VALUES (?,?,?,?)",
                         (e["stage"], e["text"], e["expect"], e.get("note", "")))
        conn.execute("INSERT INTO catalog_meta(key, value) VALUES ('seeded:guard_examples', 'done')")


# --- reading -----------------------------------------------------------------------------------------

def _load() -> dict:
    with db.connect() as conn:
        sets = [{**dict(r), "rules": json.loads(r["rules"]), "test_report": json.loads(r["test_report"])}
                for r in conn.execute("SELECT * FROM guard_rule_sets ORDER BY version DESC")]
        examples = [dict(r) for r in conn.execute("SELECT * FROM guard_examples ORDER BY stage, id")]
    return {"sets": sets, "examples": examples}


def _state() -> dict:
    return db.cached("guards", _load)


def active_rules() -> dict:
    active = next((s for s in _state()["sets"] if s["status"] == "active"), None)
    if active is None:
        raise GuardError("no active guard rule set")
    return active["rules"]


def compiled() -> dict:
    """The active rules compiled once per cache generation."""
    def build():
        rules = active_rules()
        return {
            "pre": [{**group, "regex": [re.compile(p, re.IGNORECASE) for p in group["patterns"]]} for group in rules["pre"]],
            "post": {k: re.compile(v, re.IGNORECASE) for k, v in rules["post"].items()},
            "violation_reason": rules.get("violation_reason", {}),
        }
    return db.cached("guards_compiled", build)


def describe() -> dict:
    st = _state()
    return {"versions": st["sets"], "examples": st["examples"],
            "active_version": next((s["version"] for s in st["sets"] if s["status"] == "active"), None)}


# --- gate --------------------------------------------------------------------------------------------

def _validate_shape(rules: dict) -> list[str]:
    problems = []
    if not isinstance(rules.get("pre"), list) or not rules["pre"]:
        problems.append("pre must be a non-empty list of categories")
    for group in rules.get("pre") or []:
        for key in ("category", "reason", "patterns"):
            if key not in group:
                problems.append(f"a pre category is missing '{key}'")
        if not group.get("patterns"):
            problems.append(f"pre category {group.get('category')!r} has no patterns")
    post = rules.get("post") or {}
    for name in POST_RULES:
        if not isinstance(post.get(name), str) or not post.get(name).strip():
            problems.append(f"post rule {name!r} is missing")
    return problems


def gate(rules: dict, examples: list[dict]) -> dict:
    checks = []

    def add(name, ok, detail=""):
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    shape = _validate_shape(rules)
    add("rule set is complete", not shape, "; ".join(shape))
    if shape:
        return {"passed": False, "checks": checks}
    compiled_pre, compiled_post, bad = [], {}, []
    for group in rules["pre"]:
        regs = []
        for p in group["patterns"]:
            try:
                regs.append(re.compile(p, re.IGNORECASE))
            except re.error as exc:
                bad.append(f"{group['category']}: {p!r} ({exc})")
        compiled_pre.append((group["category"], regs))
    for name in POST_RULES:
        try:
            compiled_post[name] = re.compile(rules["post"][name], re.IGNORECASE)
        except re.error as exc:
            bad.append(f"{name}: ({exc})")
    add("every pattern is a valid regular expression", not bad, "; ".join(bad))
    if bad:
        return {"passed": False, "checks": checks}

    def pre_category(text):
        for category, regs in compiled_pre:
            if any(r.search(text) for r in regs):
                return category
        return "pass"

    for e in examples:
        if e["stage"] == "pre":
            got = pre_category(e["text"])
            add(f"pre example #{e.get('id')}: {e['text'][:60]}", got == e["expect"], f"expected {e['expect']}, got {got}")
        else:
            negate = e["expect"].startswith("!")
            rule = e["expect"].lstrip("!")
            if rule not in compiled_post:
                add(f"post example #{e.get('id')}", False, f"unknown rule {rule!r}")
                continue
            hit = bool(compiled_post[rule].search(e["text"]))
            add(f"post example #{e.get('id')}: {e['text'][:60]}", hit != negate,
                f"{rule} {'matched' if hit else 'did not match'}; expected it {'not ' if negate else ''}to match")
    covered = {e["expect"] for e in examples if e["stage"] == "pre"}
    for category, _ in compiled_pre:
        add(f"category {category} has a must-catch example", category in covered,
            "" if category in covered else "add an example this category must catch, so a future edit cannot silently disable it")
    add("at least one must-pass example", "pass" in covered, "" if "pass" in covered else "add an ordinary ticket that must not be blocked")
    return {"passed": all(c["passed"] for c in checks), "checks": checks}


def test(rules: dict) -> dict:
    return gate(rules, _state()["examples"])


# --- writes ------------------------------------------------------------------------------------------

def create_draft(rules: dict, note: str, actor: str) -> dict:
    report = test(rules)
    with db.connect() as conn:
        version = conn.execute("SELECT COALESCE(MAX(version), 0) FROM guard_rule_sets").fetchone()[0] + 1
        status = "draft" if report["passed"] else "rejected"
        conn.execute("INSERT INTO guard_rule_sets(version, rules, status, note, test_report, created_by) VALUES (?,?,?,?,?,?)",
                     (version, json.dumps(rules), status, note.strip()[:500], json.dumps(report), actor))
        db.log_change(conn, actor, "guard_rules", str(version), "draft", None, {"passed": report["passed"]})
    return {"version": version, "status": status, "test_report": report}


def activate(version: int, actor: str) -> dict:
    target = next((s for s in _state()["sets"] if s["version"] == version), None)
    if target is None:
        raise GuardError(f"no guard rule version {version}")
    if target["status"] == "active":
        return {"version": version, "status": "active"}
    report = test(target["rules"])     # examples may have been added since the version was saved
    with db.connect() as conn:
        if not report["passed"]:
            conn.execute("UPDATE guard_rule_sets SET test_report=? WHERE version=?", (json.dumps(report), version))
            db.bump(conn)
        else:
            conn.execute("UPDATE guard_rule_sets SET status='retired' WHERE status='active'")
            conn.execute("UPDATE guard_rule_sets SET status='active', activated_at=datetime('now'), test_report=? WHERE version=?",
                         (json.dumps(report), version))
            db.log_change(conn, actor, "guard_rules", str(version), "activate", None, None)
    if not report["passed"]:
        raise GuardError("this version does not pass the examples: " + "; ".join(c["check"] for c in report["checks"] if not c["passed"]))
    return {"version": version, "status": "active"}


def delete_version(version: int, actor: str) -> None:
    target = next((s for s in _state()["sets"] if s["version"] == version), None)
    if target is None:
        raise GuardError(f"no guard rule version {version}")
    if target["status"] == "active":
        raise GuardError("the active version cannot be deleted; activate another version first")
    with db.connect() as conn:
        conn.execute("DELETE FROM guard_rule_sets WHERE version=?", (version,))
        db.log_change(conn, actor, "guard_rules", str(version), "delete", None, None)


def save_example(example_id: int | None, stage: str, text: str, expect: str, note: str, actor: str) -> dict:
    if stage not in ("pre", "post"):
        raise GuardError("stage must be pre or post")
    if not text.strip():
        raise GuardError("text is required")
    if stage == "post" and expect.lstrip("!") not in POST_RULES:
        raise GuardError(f"post examples expect one of {list(POST_RULES)}, optionally prefixed with !")
    if stage == "pre":
        cats = {g["category"] for g in active_rules()["pre"]} | {"pass"}
        if expect not in cats:
            raise GuardError(f"pre examples expect one of {sorted(cats)}")
    # the live rules must still pass with this example: otherwise it documents a gap, which is a draft-rules job
    trial = [e for e in _state()["examples"] if e["id"] != example_id] + [{"id": example_id or 0, "stage": stage, "text": text, "expect": expect}]
    report = gate(active_rules(), trial)
    with db.connect() as conn:
        if example_id is None:
            cur = conn.execute("INSERT INTO guard_examples(stage, text, expect, note, created_by) VALUES (?,?,?,?,?)",
                               (stage, text.strip(), expect, note.strip(), actor))
            example_id = cur.lastrowid
            action = "create"
        else:
            if not conn.execute("SELECT 1 FROM guard_examples WHERE id=?", (example_id,)).fetchone():
                raise GuardError(f"no example {example_id}")
            conn.execute("UPDATE guard_examples SET stage=?, text=?, expect=?, note=? WHERE id=?",
                         (stage, text.strip(), expect, note.strip(), example_id))
            action = "update"
        db.log_change(conn, actor, "guard_example", str(example_id), action, None, {"stage": stage, "expect": expect})
    return {"id": example_id, "live_rules_pass": report["passed"], "test_report": report}


def delete_example(example_id: int, actor: str) -> None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM guard_examples WHERE id=?", (example_id,)).fetchone()
        if row is None:
            raise GuardError(f"no example {example_id}")
        remaining = [e for e in _state()["examples"] if e["id"] != example_id]
        report = gate(active_rules(), remaining)
        failing_coverage = [c for c in report["checks"] if not c["passed"] and ("must-catch" in c["check"] or "must-pass" in c["check"])]
        if failing_coverage:
            raise GuardError("deleting it would leave " + failing_coverage[0]["check"].replace("has a", "without a"))
        conn.execute("DELETE FROM guard_examples WHERE id=?", (example_id,))
        db.log_change(conn, actor, "guard_example", str(example_id), "delete", dict(row), None)

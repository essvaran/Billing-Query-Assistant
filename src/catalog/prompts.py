"""Versioned prompts, read from the catalog.

An edit never changes the live text in place. It is saved as a new DRAFT version, the test gate runs on it, and an
admin activates it only if the gate passed; the previous active version is retired and can be restored the same way.

Templates use {{name}} placeholders (declared per prompt). render() fills them; the gate checks that every declared
placeholder is present and no undeclared one is, that required phrases (safety rules the code relies on) survive the
edit, and that the length is within bounds.
"""
import json
import re
import sqlite3

from src.catalog import db

_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")


class PromptError(ValueError):
    pass


def seed(conn: sqlite3.Connection) -> None:
    manifest = db.read_json("prompts/manifest.json")["prompts"]
    for p in manifest:
        conn.execute(
            "INSERT INTO prompts(name, label, description, used_by, placeholders, required_phrases) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET label=excluded.label, description=excluded.description, used_by=excluded.used_by, "
            "placeholders=excluded.placeholders, required_phrases=excluded.required_phrases",
            (p["name"], p["label"], p["description"], p["used_by"], json.dumps(p["placeholders"]), json.dumps(p["required_phrases"])))
        if not conn.execute("SELECT 1 FROM prompt_versions WHERE name=?", (p["name"],)).fetchone():
            body = (db.SEED_DIR / "prompts" / p["file"]).read_text(encoding="utf-8")
            report = gate_for(p, body)
            conn.execute("INSERT INTO prompt_versions(name, version, body, status, note, test_report, activated_at) "
                         "VALUES (?,?,?,'active','seeded from the code',?,datetime('now'))",
                         (p["name"], int(p.get("start_version", 1)), body, json.dumps(report)))


def _load() -> dict:
    with db.connect() as conn:
        meta = {r["name"]: {**dict(r), "placeholders": json.loads(r["placeholders"]),
                            "required_phrases": json.loads(r["required_phrases"])}
                for r in conn.execute("SELECT * FROM prompts ORDER BY name")}
        for name in meta:
            meta[name]["versions"] = [{**dict(v), "test_report": json.loads(v["test_report"])} for v in conn.execute(
                "SELECT * FROM prompt_versions WHERE name=? ORDER BY version DESC", (name,))]
    return meta


def _all() -> dict:
    return db.cached("prompts", _load)


def describe() -> list[dict]:
    out = []
    for name, p in _all().items():
        active = next((v for v in p["versions"] if v["status"] == "active"), None)
        out.append({k: p[k] for k in ("name", "label", "description", "used_by", "placeholders", "required_phrases", "min_chars", "max_chars")}
                   | {"active_version": active["version"] if active else None, "versions": p["versions"]})
    return out


def body(name: str) -> str:
    p = _all().get(name)
    if p is None:
        raise PromptError(f"unknown prompt {name!r}")
    active = next((v for v in p["versions"] if v["status"] == "active"), None)
    if active is None:
        raise PromptError(f"prompt {name!r} has no active version")
    return active["body"]


def active_version(name: str) -> int:
    p = _all().get(name)
    active = next((v for v in (p or {}).get("versions", []) if v["status"] == "active"), None)
    if active is None:
        raise PromptError(f"prompt {name!r} has no active version")
    return active["version"]


def render(name: str, **values) -> str:
    text = body(name)
    declared = set(_all()[name]["placeholders"])
    missing = declared - set(values)
    if missing:
        raise PromptError(f"prompt {name!r} needs values for {sorted(missing)}")
    return _PLACEHOLDER.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), text)


# --- test gate ---------------------------------------------------------------------------------------

def gate_for(meta: dict, text: str) -> dict:
    checks = []

    def add(name, ok, detail=""):
        checks.append({"check": name, "passed": bool(ok), "detail": detail})

    minc, maxc = meta.get("min_chars", 1), meta.get("max_chars", 20000)
    add("length", minc <= len(text.strip()) <= maxc, f"{len(text.strip())} characters (allowed {minc} to {maxc})")
    found = set(_PLACEHOLDER.findall(text))
    declared = set(meta["placeholders"] if isinstance(meta["placeholders"], list) else json.loads(meta["placeholders"]))
    add("placeholders present", declared <= found, "missing: " + ", ".join(sorted(declared - found)) if declared - found else "")
    add("no unknown placeholders", found <= declared, "unknown: " + ", ".join(sorted(found - declared)) if found - declared else "")
    phrases = meta["required_phrases"] if isinstance(meta["required_phrases"], list) else json.loads(meta["required_phrases"])
    lowered = text.lower()
    for phrase in phrases:
        add(f"keeps required phrase: {phrase}", phrase.lower() in lowered,
            "" if phrase.lower() in lowered else "the application relies on this text; put it back or ask a developer")
    bad = sorted({c for c in text if ord(c) > 126})
    add("plain ASCII", not bad, ("characters: " + " ".join(f"U+{ord(c):04X}" for c in bad)) if bad else "")
    return {"passed": all(c["passed"] for c in checks), "checks": checks}


def test(name: str, text: str) -> dict:
    p = _all().get(name)
    if p is None:
        raise PromptError(f"unknown prompt {name!r}")
    return gate_for(p, text)


# --- writes ------------------------------------------------------------------------------------------

def create_draft(name: str, text: str, note: str, actor: str) -> dict:
    p = _all().get(name)
    if p is None:
        raise PromptError(f"unknown prompt {name!r}")
    report = gate_for(p, text)
    with db.connect() as conn:
        version = (conn.execute("SELECT COALESCE(MAX(version), 0) FROM prompt_versions WHERE name=?", (name,)).fetchone()[0]) + 1
        conn.execute("INSERT INTO prompt_versions(name, version, body, status, note, test_report, created_by) VALUES (?,?,?,?,?,?,?)",
                     (name, version, text, "draft" if report["passed"] else "rejected", note.strip()[:500], json.dumps(report), actor))
        db.log_change(conn, actor, "prompt", f"{name}@{version}", "draft", None, {"passed": report["passed"]})
    return {"name": name, "version": version, "status": "draft" if report["passed"] else "rejected", "test_report": report}


def activate(name: str, version: int, actor: str) -> dict:
    p = _all().get(name)
    if p is None:
        raise PromptError(f"unknown prompt {name!r}")
    target = next((v for v in p["versions"] if v["version"] == version), None)
    if target is None:
        raise PromptError(f"{name} has no version {version}")
    if target["status"] == "active":
        return {"name": name, "version": version, "status": "active"}
    report = gate_for(p, target["body"])     # re-run: the rules may have changed since the version was saved
    if not report["passed"]:
        with db.connect() as conn:
            conn.execute("UPDATE prompt_versions SET test_report=? WHERE name=? AND version=?", (json.dumps(report), name, version))
            db.bump(conn)
        raise PromptError("this version does not pass the checks: " + "; ".join(c["check"] for c in report["checks"] if not c["passed"]))
    with db.connect() as conn:
        conn.execute("UPDATE prompt_versions SET status='retired' WHERE name=? AND status='active'", (name,))
        conn.execute("UPDATE prompt_versions SET status='active', activated_at=datetime('now'), test_report=? WHERE name=? AND version=?",
                     (json.dumps(report), name, version))
        db.log_change(conn, actor, "prompt", f"{name}@{version}", "activate", None, None)
    return {"name": name, "version": version, "status": "active"}


def delete_version(name: str, version: int, actor: str) -> None:
    p = _all().get(name)
    target = next((v for v in (p or {}).get("versions", []) if v["version"] == version), None)
    if target is None:
        raise PromptError(f"{name} has no version {version}")
    if target["status"] == "active":
        raise PromptError("the active version cannot be deleted; activate another version first")
    with db.connect() as conn:
        conn.execute("DELETE FROM prompt_versions WHERE name=? AND version=?", (name, version))
        db.log_change(conn, actor, "prompt", f"{name}@{version}", "delete", {"status": target["status"]}, None)

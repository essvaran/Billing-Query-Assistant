"""First-run seeds for the catalog, from data/seed/. Safe to run on every start.

Rules, so an admin's edits survive restarts and upgrades:
- reference values are written only when their category is created; category metadata (label, description, form
  schema) is refreshed from the seed because it describes the code, not the data;
- a setting is added when its key is missing; its value is never overwritten, its metadata is refreshed;
- model prices, prompts, guard rules and eval data are imported once (a flag in catalog_meta records it).
"""
import json
import sqlite3

from src.catalog import db


def apply(conn: sqlite3.Connection) -> None:
    _reference(conn)
    _settings(conn)
    _once(conn, "seeded:model_prices", _prices)
    from src.catalog import prompts, guards, eval_store
    prompts.seed(conn)
    guards.seed(conn)
    _once(conn, "seeded:eval", eval_store.import_files)


def _once(conn: sqlite3.Connection, flag: str, fn) -> None:
    if conn.execute("SELECT 1 FROM catalog_meta WHERE key=?", (flag,)).fetchone():
        return
    fn(conn)
    conn.execute("INSERT INTO catalog_meta(key, value) VALUES (?, 'done')", (flag,))


def _reference(conn: sqlite3.Connection) -> None:
    for cat in db.read_json("reference.json")["categories"]:
        exists = conn.execute("SELECT 1 FROM ref_categories WHERE category=?", (cat["category"],)).fetchone()
        conn.execute(
            "INSERT INTO ref_categories(category, label, description, codes_editable, meta_schema, default_meta) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(category) DO UPDATE SET label=excluded.label, "
            "description=excluded.description, codes_editable=excluded.codes_editable, "
            "meta_schema=excluded.meta_schema, default_meta=excluded.default_meta",
            (cat["category"], cat["label"], cat.get("description", ""), int(cat.get("codes_editable", True)),
             json.dumps(cat.get("meta_schema", {})), json.dumps(cat.get("default_meta", {}))))
        if exists:
            continue
        for i, v in enumerate(cat["values"]):
            conn.execute(
                "INSERT OR IGNORE INTO ref_values(category, code, label, description, sort_order, active, system, meta) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (cat["category"], v["code"], v["label"], v.get("description", ""), (i + 1) * 10,
                 int(v.get("active", True)), int(v.get("system", False)), json.dumps(v.get("meta", {}))))


def _settings(conn: sqlite3.Connection) -> None:
    for s in db.read_json("settings.json")["settings"]:
        default = json.dumps(s["value"])
        conn.execute(
            "INSERT INTO settings(key, value, type, min_value, max_value, group_name, label, description, env, restart, default_value) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET type=excluded.type, min_value=excluded.min_value, "
            "max_value=excluded.max_value, group_name=excluded.group_name, label=excluded.label, "
            "description=excluded.description, env=excluded.env, restart=excluded.restart, default_value=excluded.default_value",
            (s["key"], default, s["type"], s.get("min"), s.get("max"), s["group"], s["label"], s.get("description", ""),
             s.get("env"), int(s.get("restart", False)), default))


def _prices(conn: sqlite3.Connection) -> None:
    for p in db.read_json("model_prices.json")["prices"]:
        conn.execute("INSERT OR IGNORE INTO model_prices(model, input_per_1m, output_per_1m, source, checked_on) VALUES (?,?,?,?,?)",
                     (p["model"], p["input_per_1m"], p["output_per_1m"], p.get("source", ""), p.get("checked_on", "")))

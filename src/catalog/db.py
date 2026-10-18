"""The catalog database: everything the app is configured with and measured by.

Reference lists, runtime settings, model prices, versioned prompts and guard rules, and evaluation data live in one
SQLite file (data/catalog.db, or CATALOG_DB_PATH). Every process that needs them (the API, the CLI, both MCP servers,
the eval runner) opens the same file.

First run seeds the tables from data/seed/*.json. A seed value is written only when its table or category is first
created, so an admin's later edit or delete is never undone by a restart.

Reads are cached per process. Every write bumps a version number; readers compare it at most every
CACHE_CHECK_S seconds, so an edit made in the API reaches an MCP server process within a couple of seconds.
"""
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from src.config import PROJECT_ROOT

SEED_DIR = PROJECT_ROOT / "data" / "seed"
DB_PATH = Path(os.getenv("CATALOG_DB_PATH", PROJECT_ROOT / "data" / "catalog.db"))
CACHE_CHECK_S = 2.0

_SCHEMA = """
CREATE TABLE IF NOT EXISTS catalog_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS ref_categories (
    category       TEXT PRIMARY KEY,
    label          TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    codes_editable INTEGER NOT NULL DEFAULT 1,
    meta_schema    TEXT NOT NULL DEFAULT '{}',
    default_meta   TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS ref_values (
    category    TEXT NOT NULL REFERENCES ref_categories(category) ON DELETE CASCADE,
    code        TEXT NOT NULL,
    label       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    active      INTEGER NOT NULL DEFAULT 1,
    system      INTEGER NOT NULL DEFAULT 0,
    meta        TEXT NOT NULL DEFAULT '{}',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by  TEXT NOT NULL DEFAULT 'seed',
    PRIMARY KEY (category, code)
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    type        TEXT NOT NULL CHECK(type IN ('int','float','str','bool','json')),
    min_value   REAL,
    max_value   REAL,
    group_name  TEXT NOT NULL,
    label       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    env         TEXT,
    restart     INTEGER NOT NULL DEFAULT 0,
    default_value TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by  TEXT NOT NULL DEFAULT 'seed'
);

CREATE TABLE IF NOT EXISTS model_prices (
    model         TEXT PRIMARY KEY,
    input_per_1m  REAL NOT NULL CHECK(input_per_1m >= 0),
    output_per_1m REAL NOT NULL CHECK(output_per_1m >= 0),
    source        TEXT NOT NULL DEFAULT '',
    checked_on    TEXT NOT NULL DEFAULT '',
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by    TEXT NOT NULL DEFAULT 'seed'
);

CREATE TABLE IF NOT EXISTS prompts (
    name             TEXT PRIMARY KEY,
    label            TEXT NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    used_by          TEXT NOT NULL DEFAULT '',
    placeholders     TEXT NOT NULL DEFAULT '[]',
    required_phrases TEXT NOT NULL DEFAULT '[]',
    min_chars        INTEGER NOT NULL DEFAULT 1,
    max_chars        INTEGER NOT NULL DEFAULT 20000
);
CREATE TABLE IF NOT EXISTS prompt_versions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL REFERENCES prompts(name) ON DELETE CASCADE,
    version      INTEGER NOT NULL,
    body         TEXT NOT NULL,
    status       TEXT NOT NULL CHECK(status IN ('draft','active','retired','rejected')),
    note         TEXT NOT NULL DEFAULT '',
    test_report  TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    created_by   TEXT NOT NULL DEFAULT 'seed',
    activated_at TEXT,
    UNIQUE(name, version)
);

CREATE TABLE IF NOT EXISTS guard_rule_sets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    version      INTEGER NOT NULL UNIQUE,
    rules        TEXT NOT NULL,
    status       TEXT NOT NULL CHECK(status IN ('draft','active','retired','rejected')),
    note         TEXT NOT NULL DEFAULT '',
    test_report  TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    created_by   TEXT NOT NULL DEFAULT 'seed',
    activated_at TEXT
);
CREATE TABLE IF NOT EXISTS guard_examples (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    stage      TEXT NOT NULL CHECK(stage IN ('pre','post')),
    text       TEXT NOT NULL,
    expect     TEXT NOT NULL,
    note       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by TEXT NOT NULL DEFAULT 'seed'
);

CREATE TABLE IF NOT EXISTS eval_cases (
    case_id    TEXT PRIMARY KEY,
    suite      TEXT NOT NULL,
    slice      TEXT NOT NULL DEFAULT '',
    data       TEXT NOT NULL,
    active     INTEGER NOT NULL DEFAULT 1,
    position   INTEGER NOT NULL DEFAULT 0,
    source     TEXT NOT NULL DEFAULT 'seed',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by TEXT NOT NULL DEFAULT 'seed'
);
CREATE INDEX IF NOT EXISTS idx_eval_cases_suite ON eval_cases(suite, position);
CREATE TABLE IF NOT EXISTS eval_runs (
    tag        TEXT PRIMARY KEY,
    suite      TEXT NOT NULL DEFAULT 'main',
    status     TEXT NOT NULL CHECK(status IN ('complete','partial')),
    summary    TEXT NOT NULL DEFAULT '{}',
    settings   TEXT NOT NULL DEFAULT '{}',
    notes      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS eval_results (
    tag      TEXT NOT NULL REFERENCES eval_runs(tag) ON DELETE CASCADE,
    case_id  TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    row      TEXT NOT NULL,
    PRIMARY KEY (tag, case_id)
);
CREATE TABLE IF NOT EXISTS eval_labels (
    case_id   TEXT PRIMARY KEY,
    label     TEXT NOT NULL CHECK(label IN ('GOOD','NOT_GOOD')),
    reply_sha TEXT,
    tag       TEXT NOT NULL DEFAULT '',
    labeler   TEXT NOT NULL DEFAULT '',
    at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS change_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    at        TEXT NOT NULL DEFAULT (datetime('now')),
    actor     TEXT NOT NULL,
    entity    TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action    TEXT NOT NULL,
    before    TEXT,
    after     TEXT
);
CREATE INDEX IF NOT EXISTS idx_change_log_at ON change_log(at);
"""

_lock = threading.RLock()
_ready_for: str | None = None
_cache: dict = {"version": None, "checked": 0.0, "data": {}}


@contextmanager
def connect():
    """A connection with the schema guaranteed and seeds applied. Commits on success."""
    ensure()
    conn = _raw()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _raw() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure() -> None:
    """Create the schema and apply first-run seeds once per process and database path."""
    global _ready_for
    key = str(DB_PATH)
    if _ready_for == key:
        return
    with _lock:
        if _ready_for == key:
            return
        conn = _raw()
        try:
            conn.executescript(_SCHEMA)
            from src.catalog import seed
            seed.apply(conn)
            conn.execute("INSERT OR IGNORE INTO catalog_meta(key, value) VALUES ('version', '1')")
            conn.commit()
        finally:
            conn.close()
        _ready_for = key
        invalidate()


def bump(conn: sqlite3.Connection) -> None:
    """Call inside every write transaction: tells every process its cache is stale."""
    conn.execute("UPDATE catalog_meta SET value = CAST(value AS INTEGER) + 1 WHERE key = 'version'")
    invalidate()


def log_change(conn: sqlite3.Connection, actor: str, entity: str, entity_id: str, action: str,
               before=None, after=None) -> None:
    conn.execute("INSERT INTO change_log(actor, entity, entity_id, action, before, after) VALUES (?,?,?,?,?,?)",
                 (actor, entity, str(entity_id), action,
                  None if before is None else json.dumps(before, default=str),
                  None if after is None else json.dumps(after, default=str)))
    bump(conn)


def invalidate() -> None:
    _cache["version"] = None
    _cache["checked"] = 0.0
    _cache["data"] = {}


def cached(name: str, loader):
    """Per-process cache for a whole table or derived structure, refreshed when any process writes."""
    now = time.monotonic()
    if now - _cache["checked"] > CACHE_CHECK_S or _cache["version"] is None:
        ensure()
        conn = _raw()
        try:
            row = conn.execute("SELECT value FROM catalog_meta WHERE key='version'").fetchone()
        finally:
            conn.close()
        version = row["value"] if row else "0"
        if version != _cache["version"]:
            _cache["data"] = {}
            _cache["version"] = version
        _cache["checked"] = now
    if name not in _cache["data"]:
        _cache["data"][name] = loader()
    return _cache["data"][name]


def use_path(path: Path) -> None:
    """Point this process at another catalog file (tests, tools)."""
    global DB_PATH, _ready_for
    DB_PATH = Path(path)
    _ready_for = None
    invalidate()


def read_json(name: str) -> dict:
    return json.loads((SEED_DIR / name).read_text(encoding="utf-8"))

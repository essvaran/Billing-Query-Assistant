"""SQLite database — schema init, context manager, and initial seed."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"


@contextmanager
def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # allows concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                email       TEXT    UNIQUE NOT NULL,
                role        TEXT    NOT NULL DEFAULT 'user'
                                    CHECK(role IN ('admin','user')),
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id         TEXT PRIMARY KEY,
                customer_id       TEXT NOT NULL,
                order_id          TEXT NOT NULL,
                text              TEXT NOT NULL,
                expected_verdict  TEXT CHECK(expected_verdict IN ('approve','deny','escalate') OR expected_verdict IS NULL)
            );
            CREATE TABLE IF NOT EXISTS orders (
                order_id      TEXT    PRIMARY KEY,
                purchase_date TEXT    NOT NULL,
                amount_usd    REAL    NOT NULL CHECK(amount_usd >= 0),
                status        TEXT    NOT NULL
                                      CHECK(status IN ('delivered','pending','cancelled','refunded'))
            );
            CREATE TABLE IF NOT EXISTS customers (
                customer_id  TEXT     PRIMARY KEY,
                tier         TEXT     NOT NULL
                                      CHECK(tier IN ('standard','premium','enterprise')),
                refund_days  INTEGER  NOT NULL CHECK(refund_days > 0)
            );
            CREATE TABLE IF NOT EXISTS jobs (
                job_id     TEXT PRIMARY KEY,
                user_email TEXT NOT NULL,
                status     TEXT NOT NULL CHECK(status IN ('running','done','error')),
                steps      TEXT NOT NULL DEFAULT '[]',
                result     TEXT,
                error      TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS alerts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ts         TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                trace_id   TEXT,
                reason     TEXT,
                status     TEXT NOT NULL CHECK(status IN ('sent','failed','suppressed','test')),
                detail     TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts);
            CREATE TABLE IF NOT EXISTS drills (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                trace_id   TEXT NOT NULL,
                seconds    REAL NOT NULL CHECK(seconds >= 0),
                slice      TEXT NOT NULL,
                notes      TEXT,
                user_email TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS eval_suite_runs (
                run_id         TEXT PRIMARY KEY,
                prompt_version TEXT NOT NULL,
                started_at     TEXT NOT NULL,
                finished_at    TEXT,
                total          INTEGER NOT NULL DEFAULT 0,
                passed         INTEGER NOT NULL DEFAULT 0,
                status         TEXT NOT NULL CHECK(status IN ('running','done','error')),
                source         TEXT NOT NULL,
                user_email     TEXT,
                error          TEXT
            );
            CREATE TABLE IF NOT EXISTS eval_run_results (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id   TEXT NOT NULL REFERENCES eval_suite_runs(run_id) ON DELETE CASCADE,
                case_id  TEXT NOT NULL,
                passed   INTEGER NOT NULL,
                detail   TEXT NOT NULL DEFAULT '[]',
                answer   TEXT,
                trace_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_eval_results_run ON eval_run_results(run_id);
            CREATE TABLE IF NOT EXISTS feedback (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id    TEXT NOT NULL,
                user_email  TEXT NOT NULL,
                rating      TEXT NOT NULL CHECK(rating IN ('up','down')),
                reason_code TEXT,
                comment     TEXT,
                status      TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new','reviewed')),
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                reviewed_by TEXT,
                reviewed_at TEXT,
                admin_note  TEXT,
                UNIQUE(trace_id, user_email)
            );
            CREATE INDEX IF NOT EXISTS idx_feedback_inbox ON feedback(rating, status, created_at);
            CREATE INDEX IF NOT EXISTS idx_feedback_trace ON feedback(trace_id);
        """)
        feedback_columns = {row[1] for row in conn.execute("PRAGMA table_info(feedback)")}
        for column in ("question", "answer_preview", "prompt_version", "answered_at"):
            if column not in feedback_columns:
                conn.execute(f"ALTER TABLE feedback ADD COLUMN {column} TEXT")
        _seed_if_empty(conn)


def _seed_if_empty(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] > 0:
        return

    from api.config import ADMIN_EMAIL
    from agent.tickets import CUSTOMERS, EXPECTED, ORDERS, TICKETS

    for t in TICKETS.values():
        conn.execute(
            "INSERT OR IGNORE INTO tickets VALUES (?,?,?,?,?)",
            (t["ticket_id"], t["customer_id"], t["order_id"], t["text"], EXPECTED.get(t["ticket_id"])),
        )
    for o in ORDERS.values():
        conn.execute(
            "INSERT OR IGNORE INTO orders VALUES (?,?,?,?)",
            (o["order_id"], o["purchase_date"], o["amount_usd"], o["status"]),
        )
    for c in CUSTOMERS.values():
        conn.execute(
            "INSERT OR IGNORE INTO customers VALUES (?,?,?)",
            (c["customer_id"], c["tier"], c["refund_days"]),
        )
    conn.execute(
        "INSERT OR IGNORE INTO users (email, role) VALUES (?,?)",
        (ADMIN_EMAIL, "admin"),
    )


def insert_alert(alert_type: str, status: str, trace_id: str | None = None,
                 reason: str | None = None, detail: str | None = None):
    """Record an alert outcome (sent / failed / suppressed / test) for the alert history view."""
    from datetime import datetime, timezone

    with get_db() as conn:
        conn.execute(
            "INSERT INTO alerts (ts, alert_type, trace_id, reason, status, detail) VALUES (?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), alert_type, trace_id, reason, status, detail),
        )

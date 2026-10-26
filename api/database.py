"""SQLite database — schema init, context manager, and initial seed."""

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.getenv("APP_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "app.db"))


@contextmanager
def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # timeout = busy_timeout: a writer waits up to 10 s for another writer instead of failing at once.
    # WAL is stored in the database file, so init_db sets it once instead of every connection.
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
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
        conn.execute("PRAGMA journal_mode=WAL")  # allows reads while a write is in progress
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
            );
            CREATE TABLE IF NOT EXISTS customers (
                customer_id  TEXT     PRIMARY KEY,
                tier         TEXT     NOT NULL,
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
            CREATE TABLE IF NOT EXISTS plans (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                code                TEXT    UNIQUE NOT NULL,
                name                TEXT    NOT NULL,
                description         TEXT    NOT NULL DEFAULT '',
                price_monthly_cents INTEGER NOT NULL CHECK(price_monthly_cents >= 0),
                price_annual_cents  INTEGER NOT NULL CHECK(price_annual_cents >= 0),
                currency            TEXT    NOT NULL DEFAULT 'USD',
                tier                TEXT    NOT NULL,
                policy_version      TEXT    NOT NULL,
                refund_days         INTEGER NOT NULL CHECK(refund_days > 0),
                features            TEXT    NOT NULL DEFAULT '[]',
                max_seats           INTEGER NOT NULL DEFAULT 1 CHECK(max_seats > 0),
                is_active           INTEGER NOT NULL DEFAULT 1,
                sort_order          INTEGER NOT NULL DEFAULT 0,
                created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS addons (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                code                TEXT    UNIQUE NOT NULL,
                name                TEXT    NOT NULL,
                description         TEXT    NOT NULL DEFAULT '',
                price_monthly_cents INTEGER NOT NULL CHECK(price_monthly_cents >= 0),
                is_active           INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS billing_profiles (
                user_id       INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                company_name  TEXT NOT NULL DEFAULT '',
                billing_email TEXT NOT NULL DEFAULT '',
                address       TEXT NOT NULL DEFAULT '',
                region        TEXT NOT NULL DEFAULT 'US',
                currency      TEXT NOT NULL DEFAULT 'USD',
                billing_cycle TEXT NOT NULL DEFAULT 'monthly'
            );
            CREATE TABLE IF NOT EXISTS subscriptions (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                plan_id            INTEGER NOT NULL REFERENCES plans(id),
                billing_cycle      TEXT    NOT NULL,
                status             TEXT    NOT NULL DEFAULT 'active'
                                           CHECK(status IN ('active','cancelled','past_due')),
                seats              INTEGER NOT NULL DEFAULT 1 CHECK(seats > 0),
                started_at         TEXT    NOT NULL,
                current_period_end TEXT    NOT NULL,
                cancelled_at       TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id, status);
            CREATE TABLE IF NOT EXISTS subscription_addons (
                subscription_id INTEGER NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
                addon_id        INTEGER NOT NULL REFERENCES addons(id),
                quantity        INTEGER NOT NULL DEFAULT 1 CHECK(quantity > 0),
                PRIMARY KEY (subscription_id, addon_id)
            );
            CREATE TABLE IF NOT EXISTS invoices (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                subscription_id INTEGER REFERENCES subscriptions(id) ON DELETE SET NULL,
                number          TEXT    UNIQUE NOT NULL,
                period_start    TEXT    NOT NULL,
                period_end      TEXT    NOT NULL,
                amount_cents    INTEGER NOT NULL,
                currency        TEXT    NOT NULL DEFAULT 'USD',
                status          TEXT    NOT NULL DEFAULT 'open' CHECK(status IN ('open','paid','void')),
                line_items      TEXT    NOT NULL DEFAULT '[]',
                issued_at       TEXT    NOT NULL,
                paid_at         TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_invoices_user ON invoices(user_id, issued_at);
            CREATE TABLE IF NOT EXISTS audit_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_email TEXT NOT NULL,
                action      TEXT NOT NULL,
                target      TEXT NOT NULL DEFAULT '',
                details     TEXT NOT NULL DEFAULT '{}',
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at);
            CREATE TABLE IF NOT EXISTS ticket_histories (
                ticket_id   TEXT PRIMARY KEY,
                history     TEXT,
                escalations TEXT NOT NULL DEFAULT '[]'
            );
        """)
        feedback_columns = {row[1] for row in conn.execute("PRAGMA table_info(feedback)")}
        for column in ("question", "answer_preview", "prompt_version", "answered_at"):
            if column not in feedback_columns:
                conn.execute(f"ALTER TABLE feedback ADD COLUMN {column} TEXT")
        ticket_columns = {row[1] for row in conn.execute("PRAGMA table_info(tickets)")}
        for column, ddl in (
            ("category", "TEXT NOT NULL DEFAULT 'standard'"),
            ("expected_sequences", "TEXT NOT NULL DEFAULT '[]'"),
            ("expected_args", "TEXT NOT NULL DEFAULT '{}'"),
            ("sort_order", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if column not in ticket_columns:
                conn.execute(f"ALTER TABLE tickets ADD COLUMN {column} {ddl}")
        _drop_list_checks(conn)
        user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        for column, ddl in (
            ("password_hash", "TEXT"),
            ("full_name", "TEXT NOT NULL DEFAULT ''"),
            ("auth_provider", "TEXT NOT NULL DEFAULT 'google'"),
            ("is_active", "INTEGER NOT NULL DEFAULT 1"),
            ("customer_id", "TEXT"),
        ):
            if column not in user_columns:
                conn.execute(f"ALTER TABLE users ADD COLUMN {column} {ddl}")
        # Every request looks the user up by lower(email); without this index that is a full table scan.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email_lower ON users(lower(email))")
        _seed_billing(conn)
        _seed_if_empty(conn)
        if conn.execute("SELECT COUNT(*) FROM ticket_histories").fetchone()[0] == 0:
            for h in _seed_file("ticket_history.json")["tickets"]:
                conn.execute("INSERT INTO ticket_histories (ticket_id, history, escalations) VALUES (?,?,?)",
                             (h["ticket_id"], json.dumps(h["history"]) if h["history"] else None, json.dumps(h["escalations"])))


# Value lists (tiers, policy versions, regions, billing cycles, order statuses) are catalog reference lists, edited in
# the app; the database no longer hard-codes them in CHECK constraints. Older databases are rebuilt once without them.
_LIST_CHECKS = (
    "CHECK(status IN ('delivered','pending','cancelled','refunded'))",
    "CHECK(tier IN ('standard','premium','enterprise'))",
    "CHECK(policy_version IN ('refund-14d','refund-30d'))",
    "CHECK(region IN ('US','UK','EU','CA','AU','APAC'))",
    "CHECK(billing_cycle IN ('monthly','annual'))",
)


def _drop_list_checks(conn: sqlite3.Connection) -> None:
    import re
    for (name, sql) in conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name IN "
                                    "('orders','customers','plans','billing_profiles','subscriptions')").fetchall():
        if not any(c in sql for c in _LIST_CHECKS):
            continue
        new_sql = sql
        for c in _LIST_CHECKS:
            new_sql = re.sub(r"\s*" + re.escape(c), "", new_sql)
        new_sql = new_sql.replace(f"CREATE TABLE {name}", f"CREATE TABLE {name}__new", 1)
        indexes = [r[0] for r in conn.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL", (name,))]
        cols = ", ".join(r[1] for r in conn.execute(f"PRAGMA table_info({name})"))
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute(new_sql)
        conn.execute(f"INSERT INTO {name}__new ({cols}) SELECT {cols} FROM {name}")
        conn.execute(f"DROP TABLE {name}")
        conn.execute(f"ALTER TABLE {name}__new RENAME TO {name}")
        for idx in indexes:
            conn.execute(idx)
        conn.execute("PRAGMA foreign_keys=ON")


def _seed_file(name: str) -> dict:
    import json
    from src.config import PROJECT_ROOT
    return json.loads((PROJECT_ROOT / "data" / "seed" / name).read_text(encoding="utf-8"))


def _seed_billing(conn: sqlite3.Connection) -> None:
    """Default plans and add-ons (data/seed/billing.json), inserted only while the tables are empty."""
    import json
    seed = _seed_file("billing.json")
    if conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0] == 0:
        for p in seed["plans"]:
            conn.execute(
                "INSERT INTO plans (code, name, description, price_monthly_cents, price_annual_cents, tier,"
                " policy_version, refund_days, features, max_seats, sort_order) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (p["code"], p["name"], p["description"], p["price_monthly_cents"], p["price_annual_cents"], p["tier"],
                 p["policy_version"], p["refund_days"], json.dumps(p["features"]), p["max_seats"], p["sort_order"]),
            )
    if conn.execute("SELECT COUNT(*) FROM addons").fetchone()[0] == 0:
        for a in seed["addons"]:
            conn.execute("INSERT INTO addons (code, name, description, price_monthly_cents) VALUES (?,?,?,?)",
                         (a["code"], a["name"], a["description"], a["price_monthly_cents"]))


def _seed_if_empty(conn: sqlite3.Connection) -> None:
    """Week 7 agent data (data/seed/week7.json). Fresh databases freeze the data's as-of date to today; older ones
    get the fixture columns filled in and their as-of date recovered from the data (see _recover_as_of)."""
    import json
    from datetime import date, timedelta
    from api.config import ADMIN_EMAIL
    from src.catalog import settings
    seed = _seed_file("week7.json")
    if conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] > 0:
        for t in seed["tickets"]:          # fill the new columns on rows that predate them
            conn.execute("UPDATE tickets SET category=?, expected_sequences=?, expected_args=?, sort_order=? "
                         "WHERE ticket_id=? AND expected_sequences='[]'",
                         (t["category"], json.dumps(t["expected_sequences"]), json.dumps(t["expected_args"]),
                          t["sort_order"], t["ticket_id"]))
        _recover_as_of(conn, seed)
        return
    as_of = str(settings.get("week7.as_of")).strip().lower()
    base = date.today() if as_of in ("", "today") else date.fromisoformat(as_of)
    for t in seed["tickets"]:
        conn.execute("INSERT OR IGNORE INTO tickets (ticket_id, customer_id, order_id, text, expected_verdict, category, "
                     "expected_sequences, expected_args, sort_order) VALUES (?,?,?,?,?,?,?,?,?)",
                     (t["ticket_id"], t["customer_id"], t["order_id"], t["text"], t.get("expected_verdict"), t["category"],
                      json.dumps(t["expected_sequences"]), json.dumps(t["expected_args"]), t["sort_order"]))
    for o in seed["orders"]:
        conn.execute("INSERT OR IGNORE INTO orders VALUES (?,?,?,?)",
                     (o["order_id"], (base - timedelta(days=o["purchase_days_ago"])).isoformat(), o["amount_usd"], o["status"]))
    for c in seed["customers"]:
        conn.execute("INSERT OR IGNORE INTO customers VALUES (?,?,?)", (c["customer_id"], c["tier"], c["refund_days"]))
    conn.execute("INSERT OR IGNORE INTO users (email, role) VALUES (?,?)", (ADMIN_EMAIL.lower(), "admin"))
    if as_of in ("", "today"):
        settings.set("week7.as_of", base.isoformat(), "seed")


def _recover_as_of(conn: sqlite3.Connection, seed: dict) -> None:
    """A database seeded before the as-of setting existed stored dates relative to the day it was created, so ages
    grew every day and expected verdicts went stale. Recover that day from an untouched seed order (its stored date
    plus its seed age); leave it alone if an admin already set it or no seed order is left unchanged."""
    from datetime import date, timedelta
    from src.catalog import settings
    if str(settings.get("week7.as_of")).strip().lower() not in ("", "today"):
        return
    for o in seed["orders"]:
        row = conn.execute("SELECT purchase_date FROM orders WHERE order_id=? AND amount_usd=?", (o["order_id"], o["amount_usd"])).fetchone()
        if row:
            recovered = date.fromisoformat(row[0]) + timedelta(days=o["purchase_days_ago"])
            settings.set("week7.as_of", recovered.isoformat(), "migration")
            return


def insert_alert(alert_type: str, status: str, trace_id: str | None = None,
                 reason: str | None = None, detail: str | None = None):
    """Record an alert outcome (sent / failed / suppressed / test) for the alert history view."""
    from datetime import datetime, timezone

    with get_db() as conn:
        conn.execute(
            "INSERT INTO alerts (ts, alert_type, trace_id, reason, status, detail) VALUES (?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), alert_type, trace_id, reason, status, detail),
        )

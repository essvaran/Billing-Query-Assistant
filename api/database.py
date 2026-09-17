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
        """)
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

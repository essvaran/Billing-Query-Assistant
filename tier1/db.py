"""Tier-1 runtime store: customers, orders, tickets, handoffs.

A separate SQLite file (data/tier1.db, git-ignored) so the tracked data/app.db is
never dirtied. Seeded from the SYNTHETIC Variant A files; the frozen as-of date
travels with the data so eval results do not drift with the calendar.
"""
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from src.config import PROJECT_ROOT, VARIANT_A_DIR

DB_PATH = Path(os.getenv("TIER1_DB_PATH", PROJECT_ROOT / "data" / "tier1.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY, name TEXT, email TEXT, address TEXT,
    region TEXT NOT NULL, plan TEXT NOT NULL,
    policy_version TEXT NOT NULL, refund_days INTEGER NOT NULL,
    standard_days INTEGER NOT NULL, express_days INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL,
    purchase_date TEXT NOT NULL, amount REAL NOT NULL, currency TEXT NOT NULL, status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, order_id TEXT NOT NULL,
    subject TEXT, body TEXT NOT NULL, kind TEXT, expected_decision TEXT,
    gold_slug TEXT, expected_policy_version TEXT
);
CREATE TABLE IF NOT EXISTS spans (
    span_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, parent_id TEXT,
    name TEXT NOT NULL, kind TEXT NOT NULL, started_at TEXT NOT NULL, duration_ms REAL NOT NULL,
    input_tokens INTEGER, output_tokens INTEGER, cost_usd REAL, status TEXT NOT NULL, attrs TEXT
);
CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id, started_at);
CREATE TABLE IF NOT EXISTS ai_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT NOT NULL, trace_id TEXT NOT NULL, created_at TEXT NOT NULL,
    decision TEXT NOT NULL, reason TEXT, cost_usd REAL, latency_ms REAL, total_tokens INTEGER,
    response_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_results_ticket ON ai_results(ticket_id, id);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT NOT NULL, trace_id TEXT, created_at TEXT NOT NULL,
    action TEXT NOT NULL, final_text TEXT, edit_ratio REAL, user_email TEXT
);
CREATE TABLE IF NOT EXISTS ticket_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT, trace_id TEXT NOT NULL, created_at TEXT NOT NULL,
    reason TEXT NOT NULL, comment TEXT, user_email TEXT, status TEXT NOT NULL DEFAULT 'open', eval_case_id TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, user_email TEXT, status TEXT NOT NULL,
    trace_id TEXT, steps TEXT NOT NULL DEFAULT '[]', result TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS handoffs (
    handoff_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, ticket_ref TEXT NOT NULL,
    reason TEXT NOT NULL, summary TEXT NOT NULL, trace_id TEXT,
    status TEXT NOT NULL DEFAULT 'queued'
);
"""

def escalation_reasons() -> list[str]:
    """Active escalation reason codes (catalog reference list 'escalation_reason')."""
    from src.catalog import ref
    return ref.codes("escalation_reason")


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(_SCHEMA)
        # additive migrations for databases created before a column existed
        have = {r[1] for r in conn.execute("PRAGMA table_info(handoffs)")}
        for column in ("claimed_by", "claimed_at"):
            if column not in have:
                conn.execute(f"ALTER TABLE handoffs ADD COLUMN {column} TEXT")


def seed_from_synthetic(force: bool = False) -> dict:
    """Load customers, orders and tickets from data/variant_a/synthetic. Idempotent."""
    init_db()
    with get_conn() as conn:
        # Account customers (CU...) are created at signup and must not count as "already seeded".
        if not force and conn.execute(
            "SELECT COUNT(*) FROM customers WHERE customer_id NOT LIKE 'CU%'"
        ).fetchone()[0]:
            return {"seeded": False}
        customers = json.loads((VARIANT_A_DIR / "customers.json").read_text(encoding="utf-8"))
        orders = json.loads((VARIANT_A_DIR / "orders.json").read_text(encoding="utf-8"))
        tickets = [
            json.loads(line)
            for line in (VARIANT_A_DIR / "tickets_300.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        conn.execute("DELETE FROM customers WHERE customer_id NOT LIKE 'CU%'")
        for table in ("orders", "tickets"):
            conn.execute(f"DELETE FROM {table}")
        for c in customers:
            conn.execute(
                "INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?,?)",
                (c["customer_id"], c["name"], c["email"], c["address"], c["region"], c["plan"],
                 c["policy_version"], c["refund_days"],
                 c["shipping_sla"]["standard_days"], c["shipping_sla"]["express_days"]),
            )
        for o in orders:
            conn.execute(
                "INSERT INTO orders VALUES (?,?,?,?,?,?)",
                (o["order_id"], o["customer_id"], o["purchase_date"], o["amount"],
                 o["currency"], o["status"]),
            )
        for t in tickets:
            conn.execute(
                "INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?)",
                (t["ticket_id"], t["customer_id"], t["order_id"], t["subject"], t["body"],
                 t["kind"], t["expected_decision"], t["gold_slug"], t["expected_policy_version"]),
            )
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('as_of', ?)", (tickets[0]["as_of"],))
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('synthetic', 'true')")
    return {"seeded": True, "customers": len(customers), "orders": len(orders), "tickets": len(tickets)}


def as_of() -> date:
    """Reference date for days since purchase: env override, else the data's frozen date, else today."""
    override = os.getenv("TIER1_AS_OF")
    if override:
        return date.fromisoformat(override)
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key='as_of'").fetchone()
        if row:
            return date.fromisoformat(row["value"])
    except sqlite3.Error:
        pass
    return date.today()


def get_customer(customer_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM customers WHERE customer_id=?", (customer_id,)).fetchone()
    return dict(row) if row else None


def customer_for_email(email: str) -> dict | None:
    """The customer account that belongs to a signed-in user, matched on the account email. This is the
    production mapping; with synthetic data it only matches if a user signs in with a customer's email."""
    if not email:
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM customers WHERE lower(email)=lower(?)", (email.strip(),)).fetchone()
    return dict(row) if row else None


def get_order(order_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
    return dict(row) if row else None


def get_ticket(ticket_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE ticket_id=?", (ticket_id,)).fetchone()
    return dict(row) if row else None


def create_handoff(ticket_ref: str, reason: str, summary: str, trace_id: str | None) -> dict:
    from src.observability.redact import redact_text

    summary = redact_text(summary)  # agent-written text can repeat what the customer pasted
    handoff_id = f"H-{uuid.uuid4().hex[:10]}"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO handoffs (handoff_id, created_at, ticket_ref, reason, summary, trace_id) "
            "VALUES (?,?,?,?,?,?)",
            (handoff_id, datetime.now(timezone.utc).isoformat(), ticket_ref, reason, summary, trace_id),
        )
    return {"handoff_id": handoff_id, "status": "queued"}


def list_handoffs(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM handoffs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]

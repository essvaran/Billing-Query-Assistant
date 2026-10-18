"""Admin CRUD for the Tier-1 data: customers, orders and sample tickets in data/tier1.db.

Value lists (regions, plan tiers, policy versions, order statuses, ticket kinds) are checked against the catalog
reference lists. A customer that still has orders, or an order that still has tickets, cannot be deleted: delete the
dependent rows first, so the assistant never meets a ticket whose order or customer is gone.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import UserOut, require_admin
from api.refcheck import RefCode, setting
from src.catalog import db as catalog_db
from tier1 import db

router = APIRouter(prefix="/api/admin/tier1", tags=["tier1-admin"])

_ID = r"^[A-Za-z0-9][A-Za-z0-9_-]{1,39}$"
_DATE = r"^\d{4}-\d{2}-\d{2}$"


def _rows(sql: str, args: tuple = ()) -> list[dict]:
    db.init_db()
    with db.get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, args)]


def _one(table: str, key: str, value: str) -> dict:
    rows = _rows(f"SELECT * FROM {table} WHERE {key}=?", (value,))
    if not rows:
        raise HTTPException(404, f"{table[:-1].capitalize()} {value} not found")
    return rows[0]


def _write(sql: str, args: tuple) -> None:
    db.init_db()
    with db.get_conn() as conn:
        conn.execute(sql, args)


def _log(admin: UserOut, table: str, key: str, action: str, before: dict | None, after: dict | None) -> None:
    """Tier-1 data edits go to the same change log as the catalog, so the Data page history covers every edit."""
    with catalog_db.connect() as conn:
        catalog_db.log_change(conn, admin.email, f"tier1:{table}", key, action, before, after)


def _search(q: str, cols: tuple[str, ...]) -> tuple[str, tuple]:
    if not q:
        return "", ()
    like = f"%{q.strip()}%"
    return " WHERE " + " OR ".join(f"{c} LIKE ?" for c in cols), tuple(like for _ in cols)


# --- customers ---------------------------------------------------------------------------------------

class CustomerIn(BaseModel):
    customer_id: Optional[str] = Field(None, pattern=_ID)
    name: str = Field("", max_length=160)
    email: str = Field("", max_length=254)
    address: str = Field("", max_length=300)
    region: RefCode("region")
    plan: RefCode("plan_tier")
    policy_version: RefCode("policy_version")
    refund_days: int = Field(ge=0, le=3650)
    standard_days: int = Field(default_factory=setting("billing.account_standard_days"), ge=1, le=365)
    express_days: int = Field(default_factory=setting("billing.account_express_days"), ge=1, le=365)


@router.get("/customers")
def list_customers(q: str = Query("", max_length=100), _admin: UserOut = Depends(require_admin)):
    where, args = _search(q, ("customer_id", "name", "email"))
    rows = _rows("SELECT c.*, (SELECT COUNT(*) FROM orders o WHERE o.customer_id=c.customer_id) AS orders "
                 f"FROM customers c{where} ORDER BY customer_id", args)
    return rows


@router.post("/customers", status_code=201)
def create_customer(body: CustomerIn, admin: UserOut = Depends(require_admin)):
    if not body.customer_id:
        raise HTTPException(422, "customer_id is required")
    if _rows("SELECT 1 FROM customers WHERE customer_id=?", (body.customer_id,)):
        raise HTTPException(409, f"Customer {body.customer_id} already exists")
    d = body.model_dump()
    _write("INSERT INTO customers (customer_id, name, email, address, region, plan, policy_version, refund_days, standard_days, express_days) "
           "VALUES (?,?,?,?,?,?,?,?,?,?)", tuple(d[k] for k in ("customer_id", "name", "email", "address", "region", "plan",
                                                                 "policy_version", "refund_days", "standard_days", "express_days")))
    row = _one("customers", "customer_id", body.customer_id)
    _log(admin, "customers", body.customer_id, "create", None, row)
    return row


@router.put("/customers/{customer_id}")
def update_customer(customer_id: str, body: CustomerIn, admin: UserOut = Depends(require_admin)):
    before = _one("customers", "customer_id", customer_id)
    d = body.model_dump()
    _write("UPDATE customers SET name=?, email=?, address=?, region=?, plan=?, policy_version=?, refund_days=?, standard_days=?, "
           "express_days=? WHERE customer_id=?", tuple(d[k] for k in ("name", "email", "address", "region", "plan", "policy_version",
                                                                      "refund_days", "standard_days", "express_days")) + (customer_id,))
    row = _one("customers", "customer_id", customer_id)
    _log(admin, "customers", customer_id, "update", before, row)
    return row


@router.delete("/customers/{customer_id}", status_code=204)
def delete_customer(customer_id: str, admin: UserOut = Depends(require_admin)):
    before = _one("customers", "customer_id", customer_id)
    n = _rows("SELECT COUNT(*) AS n FROM orders WHERE customer_id=?", (customer_id,))[0]["n"]
    if n:
        raise HTTPException(409, f"Customer {customer_id} still has {n} order(s); delete those first")
    _write("DELETE FROM customers WHERE customer_id=?", (customer_id,))
    _log(admin, "customers", customer_id, "delete", before, None)


# --- orders ------------------------------------------------------------------------------------------

class OrderIn(BaseModel):
    order_id: Optional[str] = Field(None, pattern=_ID)
    customer_id: str = Field(pattern=_ID)
    purchase_date: str = Field(pattern=_DATE)
    amount: float = Field(ge=0, le=10_000_000)
    currency: str = Field(default_factory=setting("billing.currency"), pattern=r"^[A-Z]{3}$")
    status: RefCode("tier1_order_status")


def _check_order(body: OrderIn) -> None:
    from datetime import date
    try:
        date.fromisoformat(body.purchase_date)
    except ValueError:
        raise HTTPException(422, "purchase_date is not a real date")
    _one("customers", "customer_id", body.customer_id)


@router.get("/orders")
def list_orders(q: str = Query("", max_length=100), customer_id: str = Query("", max_length=40),
                _admin: UserOut = Depends(require_admin)):
    where, args = _search(q, ("order_id", "customer_id"))
    if customer_id:
        where, args = (where + " AND" if where else " WHERE") + " customer_id=?", args + (customer_id,)
    return _rows("SELECT o.*, (SELECT COUNT(*) FROM tickets t WHERE t.order_id=o.order_id) AS tickets "
                 f"FROM orders o{where} ORDER BY order_id", args)


@router.post("/orders", status_code=201)
def create_order(body: OrderIn, admin: UserOut = Depends(require_admin)):
    if not body.order_id:
        raise HTTPException(422, "order_id is required")
    _check_order(body)
    if _rows("SELECT 1 FROM orders WHERE order_id=?", (body.order_id,)):
        raise HTTPException(409, f"Order {body.order_id} already exists")
    _write("INSERT INTO orders (order_id, customer_id, purchase_date, amount, currency, status) VALUES (?,?,?,?,?,?)",
           (body.order_id, body.customer_id, body.purchase_date, body.amount, body.currency, body.status))
    row = _one("orders", "order_id", body.order_id)
    _log(admin, "orders", body.order_id, "create", None, row)
    return row


@router.put("/orders/{order_id}")
def update_order(order_id: str, body: OrderIn, admin: UserOut = Depends(require_admin)):
    before = _one("orders", "order_id", order_id)
    _check_order(body)
    _write("UPDATE orders SET customer_id=?, purchase_date=?, amount=?, currency=?, status=? WHERE order_id=?",
           (body.customer_id, body.purchase_date, body.amount, body.currency, body.status, order_id))
    row = _one("orders", "order_id", order_id)
    _log(admin, "orders", order_id, "update", before, row)
    return row


@router.delete("/orders/{order_id}", status_code=204)
def delete_order(order_id: str, admin: UserOut = Depends(require_admin)):
    before = _one("orders", "order_id", order_id)
    n = _rows("SELECT COUNT(*) AS n FROM tickets WHERE order_id=?", (order_id,))[0]["n"]
    if n:
        raise HTTPException(409, f"Order {order_id} still has {n} ticket(s); delete those first")
    _write("DELETE FROM orders WHERE order_id=?", (order_id,))
    _log(admin, "orders", order_id, "delete", before, None)


# --- tickets -----------------------------------------------------------------------------------------

class TicketIn(BaseModel):
    ticket_id: Optional[str] = Field(None, pattern=_ID)
    customer_id: str = Field(pattern=_ID)
    order_id: str = Field(pattern=_ID)
    subject: str = Field("", max_length=300)
    body: str = Field(min_length=1, max_length=20000)
    kind: RefCode("tier1_ticket_kind")
    expected_decision: Optional[str] = Field(None, pattern=r"^(ANSWER|ESCALATE)$")
    gold_slug: str = Field("", max_length=120)
    expected_policy_version: Optional[RefCode("policy_version")] = None


def _check_ticket(body: TicketIn) -> None:
    order = _one("orders", "order_id", body.order_id)
    if order["customer_id"] != body.customer_id:
        raise HTTPException(422, f"Order {body.order_id} belongs to {order['customer_id']}, not {body.customer_id}")


@router.get("/tickets")
def list_tickets(q: str = Query("", max_length=100), kind: str = Query("", max_length=40),
                 _admin: UserOut = Depends(require_admin)):
    conds, args = [], []
    if q:
        conds.append("(ticket_id LIKE ? OR subject LIKE ? OR body LIKE ? OR customer_id LIKE ?)")
        args += [f"%{q.strip()}%"] * 4
    if kind:
        conds.append("kind=?")
        args.append(kind)
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    return _rows(f"SELECT * FROM tickets{where} ORDER BY ticket_id", tuple(args))


@router.post("/tickets", status_code=201)
def create_ticket(body: TicketIn, admin: UserOut = Depends(require_admin)):
    if not body.ticket_id:
        raise HTTPException(422, "ticket_id is required")
    _check_ticket(body)
    if _rows("SELECT 1 FROM tickets WHERE ticket_id=?", (body.ticket_id,)):
        raise HTTPException(409, f"Ticket {body.ticket_id} already exists")
    d = body.model_dump()
    _write("INSERT INTO tickets (ticket_id, customer_id, order_id, subject, body, kind, expected_decision, gold_slug, expected_policy_version) "
           "VALUES (?,?,?,?,?,?,?,?,?)", tuple(d[k] for k in ("ticket_id", "customer_id", "order_id", "subject", "body", "kind",
                                                             "expected_decision", "gold_slug", "expected_policy_version")))
    row = _one("tickets", "ticket_id", body.ticket_id)
    _log(admin, "tickets", body.ticket_id, "create", None, row)
    return row


@router.put("/tickets/{ticket_id}")
def update_ticket(ticket_id: str, body: TicketIn, admin: UserOut = Depends(require_admin)):
    before = _one("tickets", "ticket_id", ticket_id)
    _check_ticket(body)
    d = body.model_dump()
    _write("UPDATE tickets SET customer_id=?, order_id=?, subject=?, body=?, kind=?, expected_decision=?, gold_slug=?, "
           "expected_policy_version=? WHERE ticket_id=?", tuple(d[k] for k in ("customer_id", "order_id", "subject", "body", "kind",
                                                                              "expected_decision", "gold_slug", "expected_policy_version")) + (ticket_id,))
    row = _one("tickets", "ticket_id", ticket_id)
    _log(admin, "tickets", ticket_id, "update", before, row)
    return row


@router.delete("/tickets/{ticket_id}", status_code=204)
def delete_ticket(ticket_id: str, admin: UserOut = Depends(require_admin)):
    before = _one("tickets", "ticket_id", ticket_id)
    _write("DELETE FROM tickets WHERE ticket_id=?", (ticket_id,))
    _log(admin, "tickets", ticket_id, "delete", before, None)

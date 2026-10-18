"""Admin CRUD endpoints for tool-calling data (tickets, orders, customers).

All routes require an admin JWT. Mutations are logged via the standard logger.
"""

import logging
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from api.refcheck import RefCode
from api.auth import UserOut, require_admin
from api.database import get_db

log = logging.getLogger("api.admin")
router = APIRouter(prefix="/api/admin", tags=["admin"])

# ---------------------------------------------------------------------------
# Verdicts, order statuses and tiers are catalog reference lists (api.refcheck.RefCode).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TicketOut(BaseModel):
    ticket_id: str
    customer_id: str
    order_id: str
    text: str
    expected_verdict: Optional[str]
    category: str = "standard"
    expected_sequences: str = "[]"     # JSON: list of accepted tool-call sequences (trajectory eval)
    expected_args: str = "{}"          # JSON: tool -> expected arguments
    sort_order: int = 0


class TicketCreate(BaseModel):
    ticket_id: str = Field(..., pattern=r"^T\d{3,}$")
    customer_id: str = Field(..., min_length=1)
    order_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    expected_verdict: Optional[RefCode("verdict")] = None
    category: RefCode("week7_ticket_category") = "standard"
    expected_sequences: str = Field("[]", max_length=5000)
    expected_args: str = Field("{}", max_length=5000)
    sort_order: int = Field(0, ge=0, le=100000)

    @field_validator("expected_sequences", "expected_args")
    @classmethod
    def _json(cls, v):
        return _valid_json(v)


class TicketUpdate(BaseModel):
    customer_id: Optional[str] = Field(default=None, min_length=1)
    order_id: Optional[str] = Field(default=None, min_length=1)
    text: Optional[str] = Field(default=None, min_length=1)
    expected_verdict: Optional[RefCode("verdict")] = None
    category: Optional[RefCode("week7_ticket_category")] = None
    expected_sequences: Optional[str] = Field(default=None, max_length=5000)
    expected_args: Optional[str] = Field(default=None, max_length=5000)
    sort_order: Optional[int] = Field(default=None, ge=0, le=100000)

    @field_validator("expected_sequences", "expected_args")
    @classmethod
    def _json(cls, v):
        return v if v is None else _valid_json(v)


def _valid_json(v: str) -> str:
    import json
    try:
        json.loads(v)
    except ValueError:
        raise ValueError("must be valid JSON")
    return v


class OrderOut(BaseModel):
    order_id: str
    purchase_date: str
    amount_usd: float
    status: str


class OrderCreate(BaseModel):
    order_id: str = Field(..., pattern=r"^O\d{3,}$")
    purchase_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    amount_usd: float = Field(..., ge=0)
    status: RefCode("order_status")


class OrderUpdate(BaseModel):
    purchase_date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    amount_usd: Optional[float] = Field(default=None, ge=0)
    status: Optional[RefCode("order_status")] = None


class CustomerOut(BaseModel):
    customer_id: str
    tier: str
    refund_days: int


class CustomerCreate(BaseModel):
    customer_id: str = Field(..., pattern=r"^C\d{3,}$")
    tier: RefCode("plan_tier")
    refund_days: int = Field(..., gt=0)


class CustomerUpdate(BaseModel):
    tier: Optional[RefCode("plan_tier")] = None
    refund_days: Optional[int] = Field(default=None, gt=0)


class PagedResponse(BaseModel):
    items: list
    total: int
    offset: int
    limit: int


class Role(str, Enum):
    admin = "admin"
    user = "user"


class AppUserOut(BaseModel):
    id: int
    email: str
    role: str
    created_at: str
    full_name: str = ""
    auth_provider: str = "google"
    is_active: bool = True
    plan_name: Optional[str] = None
    subscription_status: Optional[str] = None


class UserRoleUpdate(BaseModel):
    role: Role


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TICKET_COLS = {"customer_id", "order_id", "text", "expected_verdict"}
_ORDER_COLS = {"purchase_date", "amount_usd", "status"}
_CUSTOMER_COLS = {"tier", "refund_days"}


def _build_update(table: str, pk_col: str, pk_val: str, fields: dict) -> None:
    allowed = {"tickets": _TICKET_COLS, "orders": _ORDER_COLS, "customers": _CUSTOMER_COLS}[table]
    safe = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not safe:
        raise HTTPException(400, "No valid fields to update")
    set_clause = ", ".join(f"{k} = ?" for k in safe)
    with get_db() as conn:
        cur = conn.execute(
            f"UPDATE {table} SET {set_clause} WHERE {pk_col} = ?",
            list(safe.values()) + [pk_val],
        )
        if cur.rowcount == 0:
            raise HTTPException(404, f"{table[:-1].capitalize()} '{pk_val}' not found")


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------

@router.get("/tickets", response_model=list[TicketOut])
def list_tickets(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: UserOut = Depends(require_admin),
):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM tickets ORDER BY sort_order, ticket_id LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/tickets/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: str, _: UserOut = Depends(require_admin)):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Ticket '{ticket_id}' not found")
    return dict(row)


@router.post("/tickets", response_model=TicketOut, status_code=201)
def create_ticket(body: TicketCreate, user: UserOut = Depends(require_admin)):
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM tickets WHERE ticket_id = ?", (body.ticket_id,)).fetchone():
            raise HTTPException(409, f"Ticket '{body.ticket_id}' already exists")
        conn.execute(
            "INSERT INTO tickets (ticket_id, customer_id, order_id, text, expected_verdict, category, expected_sequences, "
            "expected_args, sort_order) VALUES (?,?,?,?,?,?,?,?,?)",
            (body.ticket_id, body.customer_id, body.order_id, body.text, body.expected_verdict, body.category,
             body.expected_sequences, body.expected_args, body.sort_order),
        )
    log.info("Admin %s created ticket %s", user.email, body.ticket_id)
    return body.model_dump()


@router.put("/tickets/{ticket_id}", response_model=TicketOut)
def update_ticket(ticket_id: str, body: TicketUpdate, user: UserOut = Depends(require_admin)):
    fields = {k: (v.value if isinstance(v, Enum) else v) for k, v in body.model_dump().items()}
    _build_update("tickets", "ticket_id", ticket_id, fields)
    log.info("Admin %s updated ticket %s", user.email, ticket_id)
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    return dict(row)


@router.delete("/tickets/{ticket_id}", status_code=204)
def delete_ticket(ticket_id: str, user: UserOut = Depends(require_admin)):
    with get_db() as conn:
        if conn.execute("DELETE FROM tickets WHERE ticket_id = ?", (ticket_id,)).rowcount == 0:
            raise HTTPException(404, f"Ticket '{ticket_id}' not found")
    log.info("Admin %s deleted ticket %s", user.email, ticket_id)


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

@router.get("/orders", response_model=list[OrderOut])
def list_orders(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: UserOut = Depends(require_admin),
):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM orders ORDER BY order_id LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: str, _: UserOut = Depends(require_admin)):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Order '{order_id}' not found")
    return dict(row)


@router.post("/orders", response_model=OrderOut, status_code=201)
def create_order(body: OrderCreate, user: UserOut = Depends(require_admin)):
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM orders WHERE order_id = ?", (body.order_id,)).fetchone():
            raise HTTPException(409, f"Order '{body.order_id}' already exists")
        conn.execute(
            "INSERT INTO orders VALUES (?,?,?,?)",
            (body.order_id, body.purchase_date, body.amount_usd, body.status),
        )
    log.info("Admin %s created order %s", user.email, body.order_id)
    return body.model_dump()


@router.put("/orders/{order_id}", response_model=OrderOut)
def update_order(order_id: str, body: OrderUpdate, user: UserOut = Depends(require_admin)):
    fields = {k: (v.value if isinstance(v, Enum) else v) for k, v in body.model_dump().items()}
    _build_update("orders", "order_id", order_id, fields)
    log.info("Admin %s updated order %s", user.email, order_id)
    with get_db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    return dict(row)


@router.delete("/orders/{order_id}", status_code=204)
def delete_order(order_id: str, user: UserOut = Depends(require_admin)):
    with get_db() as conn:
        if conn.execute("DELETE FROM orders WHERE order_id = ?", (order_id,)).rowcount == 0:
            raise HTTPException(404, f"Order '{order_id}' not found")
    log.info("Admin %s deleted order %s", user.email, order_id)


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

@router.get("/customers", response_model=list[CustomerOut])
def list_customers(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: UserOut = Depends(require_admin),
):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM customers ORDER BY customer_id LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: str, _: UserOut = Depends(require_admin)):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Customer '{customer_id}' not found")
    return dict(row)


@router.post("/customers", response_model=CustomerOut, status_code=201)
def create_customer(body: CustomerCreate, user: UserOut = Depends(require_admin)):
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM customers WHERE customer_id = ?", (body.customer_id,)).fetchone():
            raise HTTPException(409, f"Customer '{body.customer_id}' already exists")
        conn.execute(
            "INSERT INTO customers VALUES (?,?,?)",
            (body.customer_id, body.tier, body.refund_days),
        )
    log.info("Admin %s created customer %s", user.email, body.customer_id)
    return body.model_dump()


@router.put("/customers/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: str, body: CustomerUpdate, user: UserOut = Depends(require_admin)):
    fields = {k: (v.value if isinstance(v, Enum) else v) for k, v in body.model_dump().items()}
    _build_update("customers", "customer_id", customer_id, fields)
    log.info("Admin %s updated customer %s", user.email, customer_id)
    with get_db() as conn:
        row = conn.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
    return dict(row)


@router.delete("/customers/{customer_id}", status_code=204)
def delete_customer(customer_id: str, user: UserOut = Depends(require_admin)):
    with get_db() as conn:
        if conn.execute("DELETE FROM customers WHERE customer_id = ?", (customer_id,)).rowcount == 0:
            raise HTTPException(404, f"Customer '{customer_id}' not found")
    log.info("Admin %s deleted customer %s", user.email, customer_id)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users", response_model=list[AppUserOut])
def list_users(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user: UserOut = Depends(require_admin),
):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT u.id, u.email, u.role, u.created_at, u.full_name, u.auth_provider, u.is_active,"
            " p.name AS plan_name, s.status AS subscription_status FROM users u"
            " LEFT JOIN subscriptions s ON s.id = (SELECT id FROM subscriptions WHERE user_id = u.id"
            "   ORDER BY (status = 'cancelled'), id DESC LIMIT 1)"
            " LEFT JOIN plans p ON p.id = s.plan_id"
            " ORDER BY u.created_at DESC, u.id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [{**dict(r), "is_active": bool(r["is_active"])} for r in rows]


@router.put("/users/{user_id}/role", response_model=AppUserOut)
def update_user_role(user_id: int, body: UserRoleUpdate, caller: UserOut = Depends(require_admin)):
    from api.config import ADMIN_EMAIL
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"User {user_id} not found")
        if dict(row)["email"] == ADMIN_EMAIL and body.role != Role.admin:
            raise HTTPException(400, "Cannot demote the primary admin account")
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (body.role.value, user_id))
        updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    log.info("Admin %s changed user %d role to %s", caller.email, user_id, body.role.value)
    return dict(updated)

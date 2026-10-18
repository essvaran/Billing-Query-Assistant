"""Admin management of plans, add-ons, user status, subscriptions and invoices, plus the dashboard.

Every route requires an admin. Each mutation writes an audit event that feeds the dashboard activity feed.
"""
import logging
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.account_router import SubscriptionIn
from api.refcheck import RefCode, setting
from api.auth import UserOut, require_admin
from api.billing import repo, service
from api.billing.service import BillingError
from api.config import ADMIN_EMAIL
from api.database import get_db

log = logging.getLogger("api.admin.billing")
router = APIRouter(prefix="/api/admin", tags=["admin-billing"])

_CODE = r"^[a-z0-9][a-z0-9-]{1,40}$"


class PlanIn(BaseModel):
    code: str = Field(..., pattern=_CODE)
    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field("", max_length=400)
    price_monthly_cents: int = Field(..., ge=0, le=100_000_000)
    price_annual_cents: int = Field(..., ge=0, le=1_000_000_000)
    currency: str = Field(default_factory=setting("billing.currency"), pattern=r"^[A-Z]{3}$")
    tier: RefCode("plan_tier")
    policy_version: RefCode("policy_version")
    refund_days: int = Field(..., ge=1, le=365)
    features: list[str] = Field(default_factory=list, max_length=20)
    max_seats: int = Field(1, ge=1, le=10_000)
    is_active: bool = True
    sort_order: int = 0


class PlanUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    description: Optional[str] = Field(None, max_length=400)
    price_monthly_cents: Optional[int] = Field(None, ge=0, le=100_000_000)
    price_annual_cents: Optional[int] = Field(None, ge=0, le=1_000_000_000)
    currency: Optional[str] = Field(None, pattern=r"^[A-Z]{3}$")
    tier: Optional[RefCode("plan_tier")] = None
    policy_version: Optional[RefCode("policy_version")] = None
    refund_days: Optional[int] = Field(None, ge=1, le=365)
    features: Optional[list[str]] = Field(None, max_length=20)
    max_seats: Optional[int] = Field(None, ge=1, le=10_000)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class AddonIn(BaseModel):
    code: str = Field(..., pattern=_CODE)
    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field("", max_length=400)
    price_monthly_cents: int = Field(..., ge=0, le=100_000_000)
    is_active: bool = True


class AddonUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    description: Optional[str] = Field(None, max_length=400)
    price_monthly_cents: Optional[int] = Field(None, ge=0, le=100_000_000)
    is_active: Optional[bool] = None


class StatusIn(BaseModel):
    is_active: bool


class ChargeIn(BaseModel):
    amount_cents: int = Field(..., gt=0, le=100_000_000)
    description: str = Field(..., min_length=1, max_length=200)


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except BillingError as e:
        raise HTTPException(e.status, e.message)


def _user(user_id: int) -> dict:
    row = repo.get_user(user_id)
    if row is None:
        raise HTTPException(404, f"User {user_id} not found")
    return row


# --- dashboard ----------------------------------------------------------------------------------

@router.get("/dashboard")
def dashboard(_admin: UserOut = Depends(require_admin)):
    return service.dashboard()


# --- plans --------------------------------------------------------------------------------------

@router.get("/plans")
def list_plans(_admin: UserOut = Depends(require_admin)):
    return repo.list_plans()


@router.post("/plans", status_code=201)
def create_plan(body: PlanIn, admin: UserOut = Depends(require_admin)):
    try:
        plan_id = repo.insert_plan(body.model_dump())
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"A plan with code '{body.code}' already exists")
    repo.audit(admin.email, "plan_create", body.code, {"price_monthly_cents": body.price_monthly_cents})
    return repo.get_plan(plan_id)


@router.put("/plans/{plan_id}")
def update_plan(plan_id: int, body: PlanUpdate, admin: UserOut = Depends(require_admin)):
    plan = repo.get_plan(plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found")
    fields = body.model_dump(exclude_unset=True, exclude_none=True)
    repo.update_plan(plan_id, fields)
    repo.audit(admin.email, "plan_edit", plan["code"], {k: v for k, v in fields.items() if k != "features"})
    if {"tier", "policy_version", "refund_days"} & fields.keys():
        for s in repo.list_subscriptions():
            if s["plan_id"] == plan_id and s["status"] != "cancelled":
                service.sync_customer(s["user_id"])
    return repo.get_plan(plan_id)


@router.post("/plans/{plan_id}/archive")
def archive_plan(plan_id: int, admin: UserOut = Depends(require_admin)):
    """Hide a plan from new sign-ups. Existing subscribers keep it; plans are never hard-deleted."""
    plan = repo.get_plan(plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found")
    repo.update_plan(plan_id, {"is_active": False})
    repo.audit(admin.email, "plan_archive", plan["code"], {"subscribers_kept": repo.plan_in_use(plan_id)})
    return repo.get_plan(plan_id)


# --- add-ons ------------------------------------------------------------------------------------

@router.get("/addons")
def list_addons(_admin: UserOut = Depends(require_admin)):
    return repo.list_addons()


@router.post("/addons", status_code=201)
def create_addon(body: AddonIn, admin: UserOut = Depends(require_admin)):
    try:
        addon_id = repo.insert_addon(body.model_dump())
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"An add-on with code '{body.code}' already exists")
    repo.audit(admin.email, "addon_create", body.code, {})
    return repo.get_addon(addon_id)


@router.put("/addons/{addon_id}")
def update_addon(addon_id: int, body: AddonUpdate, admin: UserOut = Depends(require_admin)):
    addon = repo.get_addon(addon_id)
    if addon is None:
        raise HTTPException(404, "Add-on not found")
    fields = body.model_dump(exclude_unset=True, exclude_none=True)
    repo.update_addon(addon_id, fields)
    repo.audit(admin.email, "addon_edit", addon["code"], fields)
    return repo.get_addon(addon_id)


# --- users --------------------------------------------------------------------------------------

@router.put("/users/{user_id}/status")
def set_user_status(user_id: int, body: StatusIn, admin: UserOut = Depends(require_admin)):
    row = _user(user_id)
    if not body.is_active and row["email"].lower() in (ADMIN_EMAIL.lower(), admin.email.lower()):
        raise HTTPException(400, "You cannot disable the primary admin or your own account")
    with get_db() as conn:
        conn.execute("UPDATE users SET is_active=? WHERE id=?", (int(body.is_active), user_id))
    repo.audit(admin.email, "user_enable" if body.is_active else "user_disable", row["email"], {})
    return {"id": user_id, "email": row["email"], "is_active": body.is_active}


@router.get("/users/{user_id}/subscription")
def user_subscription(user_id: int, _admin: UserOut = Depends(require_admin)):
    _user(user_id)
    return repo.current_subscription(user_id)


@router.put("/users/{user_id}/subscription")
def override_subscription(user_id: int, body: SubscriptionIn, admin: UserOut = Depends(require_admin)):
    """Set a user's plan, creating the subscription if they have none."""
    row = _user(user_id)
    live = repo.current_subscription(user_id)
    fn = service.change_subscription if live and live["status"] != "cancelled" else service.create_subscription
    return _run(fn, row, body.plan_id, body.billing_cycle, body.seats, body.addon_qty(), actor=admin.email)


@router.post("/users/{user_id}/invoices", status_code=201)
def manual_charge(user_id: int, body: ChargeIn, admin: UserOut = Depends(require_admin)):
    return _run(service.manual_invoice, _user(user_id), body.amount_cents, body.description, admin.email)


# --- subscriptions and invoices -----------------------------------------------------------------

@router.get("/subscriptions")
def list_subscriptions(_admin: UserOut = Depends(require_admin)):
    return repo.list_subscriptions()


@router.get("/invoices")
def list_invoices(
    user_id: Optional[int] = None,
    status: Optional[str] = Query(None, max_length=20),
    _admin: UserOut = Depends(require_admin),
):
    return repo.list_invoices(user_id=user_id, status=status)


@router.post("/invoices/{invoice_id}/void")
def void_invoice(invoice_id: int, admin: UserOut = Depends(require_admin)):
    return _run(service.set_invoice_status, invoice_id, "void", admin.email)


@router.post("/invoices/{invoice_id}/mark-paid")
def mark_paid(invoice_id: int, admin: UserOut = Depends(require_admin)):
    return _run(service.set_invoice_status, invoice_id, "paid", admin.email)

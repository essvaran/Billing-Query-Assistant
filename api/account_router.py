"""Signed-in user's own account: public pricing, billing profile, subscription and invoices.

Every route here reads and writes only the caller's own rows (the user id comes from the token, never the URL).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.refcheck import RefCode, setting
from api.auth import UserOut, get_current_user
from api.billing import repo, service
from api.billing.service import BillingError

router = APIRouter(prefix="/api/account", tags=["account"])


class ProfileIn(BaseModel):
    company_name: str = Field("", max_length=160)
    billing_email: str = Field("", max_length=254)
    address: str = Field("", max_length=300)
    region: RefCode("region") = Field(default_factory=setting("billing.default_region"))
    currency: str = Field(default_factory=setting("billing.currency"), pattern=r"^[A-Z]{3}$")
    billing_cycle: RefCode("billing_cycle") = "monthly"


class AddonSelection(BaseModel):
    addon_id: int
    quantity: int = Field(1, ge=1, le=10000)          # the real limit is the setting billing.max_addon_qty


class SubscriptionIn(BaseModel):
    plan_id: int
    billing_cycle: RefCode("billing_cycle") = "monthly"
    seats: int = Field(1, ge=1, le=1000000)           # the real limit is the setting billing.max_seats
    addons: list[AddonSelection] = Field(default_factory=list, max_length=20)

    def addon_qty(self) -> dict[int, int]:
        out: dict[int, int] = {}
        for a in self.addons:
            out[a.addon_id] = out.get(a.addon_id, 0) + a.quantity
        return out


def _me(user: UserOut) -> dict:
    row = repo.get_user_by_email(user.email)
    if row is None:
        raise HTTPException(404, "Account not found")
    return row


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except BillingError as e:
        raise HTTPException(e.status, e.message)


@router.get("/plans")
def plans():
    """Public pricing for the sign-up page: active plans and add-ons only."""
    return {"plans": repo.list_plans(active_only=True), "addons": repo.list_addons(active_only=True)}


@router.get("/profile")
def get_profile(user: UserOut = Depends(get_current_user)):
    return repo.get_profile(_me(user)["id"])


@router.put("/profile")
def put_profile(body: ProfileIn, user: UserOut = Depends(get_current_user)):
    row = _me(user)
    data = body.model_dump(mode="json")
    repo.upsert_profile(row["id"], data)
    service.sync_customer(row["id"])  # region and address feed the support assistant
    return repo.get_profile(row["id"])


@router.get("/subscription")
def get_subscription(user: UserOut = Depends(get_current_user)):
    return repo.current_subscription(_me(user)["id"])


@router.post("/subscription", status_code=201)
def subscribe(body: SubscriptionIn, user: UserOut = Depends(get_current_user)):
    return _run(service.create_subscription, _me(user), body.plan_id, body.billing_cycle, body.seats,
                body.addon_qty())


@router.put("/subscription")
def change_subscription(body: SubscriptionIn, user: UserOut = Depends(get_current_user)):
    return _run(service.change_subscription, _me(user), body.plan_id, body.billing_cycle, body.seats,
                body.addon_qty())


@router.post("/subscription/cancel")
def cancel_subscription(user: UserOut = Depends(get_current_user)):
    return _run(service.cancel_subscription, _me(user))


@router.get("/invoices")
def invoices(user: UserOut = Depends(get_current_user)):
    return repo.list_invoices(user_id=_me(user)["id"])


@router.get("/invoices/{invoice_id}")
def invoice(invoice_id: int, user: UserOut = Depends(get_current_user)):
    inv = repo.get_invoice(invoice_id)
    if inv is None or inv["user_id"] != _me(user)["id"]:
        raise HTTPException(404, "Invoice not found")  # same answer for "not yours" so ids cannot be probed
    return inv

"""Catalog API: reference lists, settings, model prices, prompts, guard rules and the change log.

Reading reference lists is open to any signed-in user (the customer UI needs reasons, regions and policy labels).
Everything else, and every write, is admin only. Every write is recorded in the catalog change log.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import UserOut, get_current_user, require_admin
from src.catalog import db, guards, prices, prompts, ref, settings

router = APIRouter(tags=["catalog"])

# settings a signed-in customer's screens need (no limits that reveal capacity or cost)
PUBLIC_SETTINGS = ("billing.max_seats", "billing.max_addon_qty", "billing.currency", "billing.default_region",
                   "feedback.max_comment")


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(400, str(exc))


# --- reference lists -----------------------------------------------------------------------------------

@router.get("/api/catalog/ref")
def all_reference(_user: UserOut = Depends(get_current_user)):
    """Every category with its values (inactive ones included, flagged), so screens can still label old records."""
    return [{k: v for k, v in c.items() if k != "default_meta"} | {"values": [{k: v for k, v in x.items() if k != "meta_raw"} for x in c["values"]]}
            for c in ref.all_categories().values()]


@router.get("/api/catalog/public-settings")
def public_settings(_user: UserOut = Depends(get_current_user)):
    return {k: settings.get(k) for k in PUBLIC_SETTINGS}


class RefValueIn(BaseModel):
    code: str | None = Field(None, max_length=60)
    label: str | None = Field(None, max_length=300)
    description: str | None = Field(None, max_length=1000)
    sort_order: int | None = Field(None, ge=0, le=100000)
    active: bool | None = None
    meta: dict[str, Any] | None = None


def _in_use(category: str, code: str) -> int:
    """How many stored records still use a code; a code in use can be switched off but not deleted."""
    from api.database import get_db
    from tier1 import db as tier1_db
    app_checks = {
        "region": ["SELECT COUNT(*) FROM billing_profiles WHERE region=?"],
        "plan_tier": ["SELECT COUNT(*) FROM plans WHERE tier=?", "SELECT COUNT(*) FROM customers WHERE tier=?"],
        "policy_version": ["SELECT COUNT(*) FROM plans WHERE policy_version=?"],
        "order_status": ["SELECT COUNT(*) FROM orders WHERE status=?"],
        "billing_cycle": ["SELECT COUNT(*) FROM subscriptions WHERE billing_cycle=?", "SELECT COUNT(*) FROM billing_profiles WHERE billing_cycle=?"],
        "docs_feedback_reason": ["SELECT COUNT(*) FROM feedback WHERE reason_code=?"],
    }
    tier1_checks = {
        "region": ["SELECT COUNT(*) FROM customers WHERE region=?"],
        "policy_version": ["SELECT COUNT(*) FROM customers WHERE policy_version=?"],
        "escalation_reason": ["SELECT COUNT(*) FROM handoffs WHERE reason=?"],
        "ticket_report_reason": ["SELECT COUNT(*) FROM ticket_feedback WHERE reason=?"],
    }
    total = 0
    with get_db() as conn:
        for q in app_checks.get(category, []):
            total += conn.execute(q, (code,)).fetchone()[0]
    if category in tier1_checks:
        tier1_db.init_db()
        with tier1_db.get_conn() as conn:
            for q in tier1_checks[category]:
                total += conn.execute(q, (code,)).fetchone()[0]
    return total


@router.post("/api/admin/catalog/ref/{category}", status_code=201)
def create_ref_value(category: str, body: RefValueIn, admin: UserOut = Depends(require_admin)):
    try:
        return ref.upsert(category, body.code or "", body.model_dump(exclude={"code"}), admin.email, create=True)
    except ref.RefError as exc:
        raise _bad(exc)


@router.put("/api/admin/catalog/ref/{category}/{code}")
def update_ref_value(category: str, code: str, body: RefValueIn, admin: UserOut = Depends(require_admin)):
    try:
        return ref.upsert(category, code, body.model_dump(exclude={"code"}), admin.email, create=False)
    except ref.RefError as exc:
        raise _bad(exc)


@router.delete("/api/admin/catalog/ref/{category}/{code}", status_code=204)
def delete_ref_value(category: str, code: str, admin: UserOut = Depends(require_admin)):
    try:
        ref.delete(category, code, admin.email, in_use=_in_use(category, code))
    except ref.RefError as exc:
        raise _bad(exc)


# --- settings -------------------------------------------------------------------------------------------

class SettingIn(BaseModel):
    value: Any


@router.get("/api/admin/catalog/settings")
def list_settings(_admin: UserOut = Depends(require_admin)):
    return settings.describe()


@router.put("/api/admin/catalog/settings/{key}")
def update_setting(key: str, body: SettingIn, admin: UserOut = Depends(require_admin)):
    try:
        return settings.set(key, body.value, admin.email)
    except settings.SettingError as exc:
        raise _bad(exc)


@router.post("/api/admin/catalog/settings/{key}/reset")
def reset_setting(key: str, admin: UserOut = Depends(require_admin)):
    try:
        return settings.reset(key, admin.email)
    except settings.SettingError as exc:
        raise _bad(exc)


# --- model prices ---------------------------------------------------------------------------------------

class PriceIn(BaseModel):
    model: str | None = Field(None, max_length=120)
    input_per_1m: float = Field(ge=0, le=10000)
    output_per_1m: float = Field(ge=0, le=10000)
    source: str = Field("", max_length=300)
    checked_on: str = Field("", max_length=20)


@router.get("/api/admin/catalog/prices")
def list_prices(_admin: UserOut = Depends(require_admin)):
    return prices.all_prices()


@router.post("/api/admin/catalog/prices", status_code=201)
def create_price(body: PriceIn, admin: UserOut = Depends(require_admin)):
    try:
        return prices.upsert(body.model or "", body.input_per_1m, body.output_per_1m, body.source, body.checked_on, admin.email, create=True)
    except prices.PriceError as exc:
        raise _bad(exc)


@router.put("/api/admin/catalog/prices/{model:path}")
def update_price(model: str, body: PriceIn, admin: UserOut = Depends(require_admin)):
    try:
        return prices.upsert(model, body.input_per_1m, body.output_per_1m, body.source, body.checked_on, admin.email, create=False)
    except prices.PriceError as exc:
        raise _bad(exc)


@router.delete("/api/admin/catalog/prices/{model:path}", status_code=204)
def delete_price(model: str, admin: UserOut = Depends(require_admin)):
    try:
        prices.delete(model, admin.email)
    except prices.PriceError as exc:
        raise _bad(exc)


# --- prompts --------------------------------------------------------------------------------------------

class PromptBody(BaseModel):
    body: str = Field(min_length=1, max_length=50000)
    note: str = Field("", max_length=500)


@router.get("/api/admin/catalog/prompts")
def list_prompts(_admin: UserOut = Depends(require_admin)):
    return prompts.describe()


@router.post("/api/admin/catalog/prompts/{name}/test")
def test_prompt(name: str, body: PromptBody, _admin: UserOut = Depends(require_admin)):
    try:
        return prompts.test(name, body.body)
    except prompts.PromptError as exc:
        raise _bad(exc)


@router.post("/api/admin/catalog/prompts/{name}/versions", status_code=201)
def draft_prompt(name: str, body: PromptBody, admin: UserOut = Depends(require_admin)):
    try:
        return prompts.create_draft(name, body.body, body.note, admin.email)
    except prompts.PromptError as exc:
        raise _bad(exc)


@router.post("/api/admin/catalog/prompts/{name}/versions/{version}/activate")
def activate_prompt(name: str, version: int, admin: UserOut = Depends(require_admin)):
    try:
        return prompts.activate(name, version, admin.email)
    except prompts.PromptError as exc:
        raise _bad(exc)


@router.delete("/api/admin/catalog/prompts/{name}/versions/{version}", status_code=204)
def delete_prompt_version(name: str, version: int, admin: UserOut = Depends(require_admin)):
    try:
        prompts.delete_version(name, version, admin.email)
    except prompts.PromptError as exc:
        raise _bad(exc)


# --- guard rules ----------------------------------------------------------------------------------------

class RulesIn(BaseModel):
    rules: dict[str, Any]
    note: str = Field("", max_length=500)


class ExampleIn(BaseModel):
    stage: str = Field(pattern="^(pre|post)$")
    text: str = Field(min_length=1, max_length=5000)
    expect: str = Field(min_length=1, max_length=60)
    note: str = Field("", max_length=300)


@router.get("/api/admin/catalog/guards")
def get_guards(_admin: UserOut = Depends(require_admin)):
    return guards.describe()


@router.post("/api/admin/catalog/guards/test")
def test_guards(body: RulesIn, _admin: UserOut = Depends(require_admin)):
    return guards.test(body.rules)


@router.post("/api/admin/catalog/guards/versions", status_code=201)
def draft_guards(body: RulesIn, admin: UserOut = Depends(require_admin)):
    return guards.create_draft(body.rules, body.note, admin.email)


@router.post("/api/admin/catalog/guards/versions/{version}/activate")
def activate_guards(version: int, admin: UserOut = Depends(require_admin)):
    try:
        return guards.activate(version, admin.email)
    except guards.GuardError as exc:
        raise _bad(exc)


@router.delete("/api/admin/catalog/guards/versions/{version}", status_code=204)
def delete_guards(version: int, admin: UserOut = Depends(require_admin)):
    try:
        guards.delete_version(version, admin.email)
    except guards.GuardError as exc:
        raise _bad(exc)


@router.post("/api/admin/catalog/guards/examples", status_code=201)
def create_example(body: ExampleIn, admin: UserOut = Depends(require_admin)):
    try:
        return guards.save_example(None, body.stage, body.text, body.expect, body.note, admin.email)
    except guards.GuardError as exc:
        raise _bad(exc)


@router.put("/api/admin/catalog/guards/examples/{example_id}")
def update_example(example_id: int, body: ExampleIn, admin: UserOut = Depends(require_admin)):
    try:
        return guards.save_example(example_id, body.stage, body.text, body.expect, body.note, admin.email)
    except guards.GuardError as exc:
        raise _bad(exc)


@router.delete("/api/admin/catalog/guards/examples/{example_id}", status_code=204)
def delete_example(example_id: int, admin: UserOut = Depends(require_admin)):
    try:
        guards.delete_example(example_id, admin.email)
    except guards.GuardError as exc:
        raise _bad(exc)


# --- change log -----------------------------------------------------------------------------------------

@router.get("/api/admin/catalog/changes")
def change_log(limit: int = Query(100, ge=1, le=1000), entity: str = Query("", max_length=60),
               _admin: UserOut = Depends(require_admin)):
    with db.connect() as conn:
        q = "SELECT * FROM change_log" + (" WHERE entity LIKE ?" if entity else "") + " ORDER BY id DESC LIMIT ?"
        args = ((entity + "%",) if entity else ()) + (limit,)
        return [dict(r) for r in conn.execute(q, args)]

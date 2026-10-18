"""Accounts, plans, subscriptions and invoices: password auth, billing rules, user and admin APIs.

Runs the real app against a temporary app.db and tier1.db. Payments are simulated, so there is nothing to mock.
"""
import os

import pytest

os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-32-chars-minimum!!")
os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")

from fastapi.testclient import TestClient

import api.database as database
from api.auth import _make_jwt
from api.config import ADMIN_EMAIL
from api.limiter import limiter
from api.main import app
from tier1 import db as tier1_db

PW = "correct-horse-battery"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(tier1_db, "DB_PATH", tmp_path / "tier1.db")
    monkeypatch.setattr(limiter, "enabled", False)
    database.init_db()
    return TestClient(app)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _signup(client, email="ann@example.com", name="Ann Lee"):
    r = client.post("/api/auth/register", json={"email": email, "password": PW, "full_name": name})
    assert r.status_code == 201, r.text
    return _auth(r.json()["token"])


def _admin(client):
    with database.get_db() as conn:
        conn.execute("INSERT OR IGNORE INTO users (email, role) VALUES (?, 'admin')", (ADMIN_EMAIL,))
    return _auth(_make_jwt(ADMIN_EMAIL, "admin"))


def _plan_id(client, code):
    return next(p["id"] for p in client.get("/api/account/plans").json()["plans"] if p["code"] == code)


def _subscribe(client, h, code="premium", cycle="monthly", seats=1, addons=()):
    return client.post("/api/account/subscription", headers=h, json={
        "plan_id": _plan_id(client, code), "billing_cycle": cycle, "seats": seats,
        "addons": [{"addon_id": a, "quantity": q} for a, q in addons]})


# --- password auth ------------------------------------------------------------------------------

def test_register_login_and_me(client):
    h = _signup(client)
    me = client.get("/api/auth/me", headers=h).json()
    assert me["email"] == "ann@example.com" and me["role"] == "user" and me["onboarded"] is False
    r = client.post("/api/auth/login", json={"email": "ANN@example.com", "password": PW})
    assert r.status_code == 200 and r.json()["user"]["role"] == "user"


def test_register_rejects_duplicates_weak_passwords_and_admin_email(client):
    _signup(client)
    dup = client.post("/api/auth/register", json={"email": "Ann@Example.com", "password": PW, "full_name": "x"})
    assert dup.status_code == 409
    weak = client.post("/api/auth/register", json={"email": "b@example.com", "password": "short", "full_name": "x"})
    assert weak.status_code == 422
    admin = client.post("/api/auth/register", json={"email": ADMIN_EMAIL, "password": PW, "full_name": "x"})
    assert admin.status_code == 409  # admin is claimed through Google only, never by password sign-up


def test_login_wrong_password_and_unknown_email_look_the_same(client):
    _signup(client)
    a = client.post("/api/auth/login", json={"email": "ann@example.com", "password": "wrong-password"})
    b = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": PW})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_disabled_user_is_locked_out_immediately_and_role_change_applies_without_new_token(client):
    h = _signup(client)
    admin = _admin(client)
    uid = next(u["id"] for u in client.get("/api/admin/users", headers=admin).json() if u["email"] == "ann@example.com")
    assert client.get("/api/admin/dashboard", headers=h).status_code == 403
    client.put(f"/api/admin/users/{uid}/role", headers=admin, json={"role": "admin"})
    assert client.get("/api/admin/dashboard", headers=h).status_code == 200  # same token, new role
    client.put(f"/api/admin/users/{uid}/role", headers=admin, json={"role": "user"})
    assert client.put(f"/api/admin/users/{uid}/status", headers=admin, json={"is_active": False}).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 403
    assert client.post("/api/auth/login", json={"email": "ann@example.com", "password": PW}).status_code == 403


def test_primary_admin_cannot_be_disabled(client):
    admin = _admin(client)
    uid = next(u["id"] for u in client.get("/api/admin/users", headers=admin).json() if u["email"] == ADMIN_EMAIL)
    assert client.put(f"/api/admin/users/{uid}/status", headers=admin, json={"is_active": False}).status_code == 400


# --- subscribe, pricing, invoices ---------------------------------------------------------------

def test_subscribe_prices_plan_seats_and_addons_and_issues_paid_invoice(client):
    h = _signup(client)
    addon_id = client.get("/api/account/plans").json()["addons"][0]["id"]
    r = _subscribe(client, h, "premium", "monthly", seats=2, addons=[(addon_id, 2)])
    assert r.status_code == 201, r.text
    assert r.json()["plan_code"] == "premium"
    inv = client.get("/api/account/invoices", headers=h).json()
    assert len(inv) == 1 and inv[0]["status"] == "paid"
    assert inv[0]["amount_cents"] == 4900 * 2 + 2500 * 2  # seats x plan + qty x add-on, in cents
    assert client.get("/api/auth/me", headers=h).json()["onboarded"] is True


def test_annual_cycle_uses_annual_price_and_twelve_months_of_addons(client):
    h = _signup(client)
    addon = client.get("/api/account/plans").json()["addons"][1]
    _subscribe(client, h, "standard", "annual", addons=[(addon["id"], 1)])
    inv = client.get("/api/account/invoices", headers=h).json()[0]
    assert inv["amount_cents"] == 19000 + addon["price_monthly_cents"] * 12


def test_cannot_subscribe_twice_or_exceed_seats(client):
    h = _signup(client)
    assert _subscribe(client, h, "standard", seats=4).status_code == 422  # standard allows 3
    assert _subscribe(client, h, "standard").status_code == 201
    assert _subscribe(client, h, "premium").status_code == 409


def test_plan_change_credits_unused_time_and_updates_the_subscription(client):
    h = _signup(client)
    _subscribe(client, h, "standard")
    r = client.put("/api/account/subscription", headers=h, json={
        "plan_id": _plan_id(client, "premium"), "billing_cycle": "monthly", "seats": 1, "addons": []})
    assert r.status_code == 200 and r.json()["plan_code"] == "premium"
    newest = client.get("/api/account/invoices", headers=h).json()[0]
    credit = [li for li in newest["line_items"] if li["kind"] == "credit"]
    assert credit and credit[0]["amount_cents"] < 0
    assert 0 < newest["amount_cents"] < 4900  # premium price less the credit for the unused standard month


def test_cancel_then_resubscribe(client):
    h = _signup(client)
    _subscribe(client, h, "standard")
    assert client.post("/api/account/subscription/cancel", headers=h).json()["status"] == "cancelled"
    assert client.get("/api/auth/me", headers=h).json()["onboarded"] is False
    assert client.post("/api/account/subscription/cancel", headers=h).status_code == 404
    assert _subscribe(client, h, "premium").status_code == 201


def test_invoice_is_a_snapshot_when_admin_edits_the_plan_price(client):
    h = _signup(client)
    admin = _admin(client)
    _subscribe(client, h, "premium")
    pid = _plan_id(client, "premium")
    assert client.put(f"/api/admin/plans/{pid}", headers=admin, json={"price_monthly_cents": 9900}).status_code == 200
    assert client.get("/api/account/invoices", headers=h).json()[0]["amount_cents"] == 4900
    assert client.get("/api/account/plans").json()["plans"][1]["price_monthly_cents"] == 9900


def test_user_cannot_read_another_users_invoice(client):
    a, b = _signup(client, "a@example.com"), _signup(client, "b@example.com")
    _subscribe(client, a, "standard")
    inv_id = client.get("/api/account/invoices", headers=a).json()[0]["id"]
    assert client.get(f"/api/account/invoices/{inv_id}", headers=a).status_code == 200
    assert client.get(f"/api/account/invoices/{inv_id}", headers=b).status_code == 404
    assert client.get("/api/account/invoices", headers=b).json() == []


# --- link to the support assistant --------------------------------------------------------------

def test_subscription_creates_the_tier1_customer_the_chat_acts_as(client):
    h = _signup(client)
    client.put("/api/account/profile", headers=h, json={"region": "UK", "billing_cycle": "monthly"})
    _subscribe(client, h, "standard")
    me = client.get("/api/tier1/me/customer", headers=h).json()
    assert me["can_choose"] is False
    assert me["customer"]["plan"] == "standard" and me["customer"]["policy_version"] == "refund-14d"
    assert me["customer"]["region"] == "UK" and me["customer"]["customer_id"].startswith("CU")
    admin = _admin(client)
    client.put("/api/account/subscription", headers=h, json={
        "plan_id": _plan_id(client, "enterprise"), "billing_cycle": "monthly", "seats": 1, "addons": []})
    me = client.get("/api/tier1/me/customer", headers=h).json()
    assert me["customer"]["plan"] == "enterprise" and me["customer"]["policy_version"] == "refund-30d"
    assert admin  # admin identity unaffected


def test_account_customer_does_not_block_or_get_wiped_by_the_synthetic_seed(client):
    h = _signup(client)
    _subscribe(client, h, "standard")
    assert tier1_db.seed_from_synthetic()["seeded"] is True
    assert tier1_db.customer_for_email("ann@example.com") is not None
    tier1_db.seed_from_synthetic(force=True)
    assert tier1_db.customer_for_email("ann@example.com") is not None


# --- admin --------------------------------------------------------------------------------------

def test_admin_routes_require_admin(client):
    h = _signup(client)
    for method, path in [("get", "/api/admin/dashboard"), ("get", "/api/admin/plans"),
                         ("get", "/api/admin/subscriptions"), ("get", "/api/admin/invoices"),
                         ("get", "/api/admin/addons")]:
        assert getattr(client, method)(path, headers=h).status_code == 403
        assert getattr(client, method)(path).status_code == 401


def test_admin_plan_crud_and_archive_keeps_subscribers(client):
    h = _signup(client)
    admin = _admin(client)
    body = {"code": "team", "name": "Team", "price_monthly_cents": 3000, "price_annual_cents": 30000,
            "tier": "premium", "policy_version": "refund-30d", "refund_days": 30, "max_seats": 10,
            "features": ["Shared inbox"]}
    r = client.post("/api/admin/plans", headers=admin, json=body)
    assert r.status_code == 201 and r.json()["features"] == ["Shared inbox"]
    assert client.post("/api/admin/plans", headers=admin, json=body).status_code == 409
    assert _subscribe(client, h, "team").status_code == 201
    pid = r.json()["id"]
    assert client.post(f"/api/admin/plans/{pid}/archive", headers=admin).json()["is_active"] is False
    assert "team" not in [p["code"] for p in client.get("/api/account/plans").json()["plans"]]
    assert client.get("/api/account/subscription", headers=h).json()["plan_code"] == "team"  # subscriber keeps it
    h2 = _signup(client, "c@example.com")
    bought = client.post("/api/account/subscription", headers=h2, json={"plan_id": pid, "seats": 1})
    assert bought.status_code == 404  # archived plans cannot be bought


def test_admin_override_manual_charge_and_invoice_state_rules(client):
    h = _signup(client)
    admin = _admin(client)
    uid = next(u["id"] for u in client.get("/api/admin/users", headers=admin).json() if u["email"] == "ann@example.com")
    r = client.put(f"/api/admin/users/{uid}/subscription", headers=admin, json={
        "plan_id": _plan_id(client, "enterprise"), "billing_cycle": "monthly", "seats": 5, "addons": []})
    assert r.status_code == 200 and r.json()["plan_code"] == "enterprise"  # created: user had none
    charge = client.post(f"/api/admin/users/{uid}/invoices", headers=admin,
                         json={"amount_cents": 1234, "description": "Setup fee"})
    assert charge.status_code == 201 and charge.json()["status"] == "open"
    iid = charge.json()["id"]
    assert client.post(f"/api/admin/invoices/{iid}/mark-paid", headers=admin).json()["status"] == "paid"
    assert client.post(f"/api/admin/invoices/{iid}/void", headers=admin).status_code == 409  # paid cannot be voided
    assert client.get("/api/auth/me", headers=h).json()["onboarded"] is True


def test_dashboard_counts_and_activity_feed(client):
    h = _signup(client)
    admin = _admin(client)
    _subscribe(client, h, "premium")
    d = client.get("/api/admin/dashboard", headers=admin).json()
    assert d["users_total"] >= 2 and d["active_subscriptions"] == 1
    assert d["mrr_cents"] == 4900 and d["revenue_30d_cents"] == 4900 and d["signups_7d"] >= 1
    assert {"subscribe", "signup"} <= {e["action"] for e in d["activity"]}
    users = client.get("/api/admin/users", headers=admin).json()
    ann = next(u for u in users if u["email"] == "ann@example.com")
    assert ann["plan_name"] == "Premium" and ann["subscription_status"] == "active" and ann["is_active"] is True


def test_public_plans_need_no_login(client):
    r = client.get("/api/account/plans")
    assert r.status_code == 200 and [p["code"] for p in r.json()["plans"]] == ["standard", "premium", "enterprise"]

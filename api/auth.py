"""Authentication: email + password accounts and Google sign-in, both issuing the same JWT session token."""

import re
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from pydantic import BaseModel, Field

from api.config import (
    ADMIN_EMAIL, GOOGLE_CLIENT_ID, JWT_ALGORITHM, JWT_EXPIRE_DAYS, JWT_SECRET, PASSWORD_AUTH_ENABLED,
)
from api.database import get_db
from api.limiter import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
# Compared against when the email is unknown so a missing account costs the same time as a wrong password.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt())


# Failed password attempts per email, so guessing one account's password is slow even from many addresses
# (the per-address limit on /login only covers one source). In process memory, like the rest of the limits.
_FAILED_WINDOW_S = 15 * 60
_FAILED_MAX = 5
_failed: dict[str, deque] = {}
_failed_lock = threading.Lock()


def _too_many_failures(email: str) -> bool:
    cutoff = time.monotonic() - _FAILED_WINDOW_S
    with _failed_lock:
        q = _failed.get(email)
        while q and q[0] < cutoff:
            q.popleft()
        return bool(q) and len(q) >= _FAILED_MAX


def _record_failure(email: str) -> None:
    with _failed_lock:
        _failed.setdefault(email, deque()).append(time.monotonic())


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GoogleLoginRequest(BaseModel):
    credential: str


class RegisterRequest(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., min_length=8, max_length=72)  # bcrypt ignores or rejects bytes past 72
    full_name: str = Field(..., min_length=1, max_length=120)


class PasswordLoginRequest(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., min_length=1, max_length=72)


class UserOut(BaseModel):
    email: str
    role: str


class MeOut(UserOut):
    full_name: str = ""
    auth_provider: str = "google"
    onboarded: bool = False


class TokenResponse(BaseModel):
    token: str
    user: UserOut


class AuthConfig(BaseModel):
    google_client_id: str
    password_auth_enabled: bool


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

JWT_ISSUER = "billing-support-api"
JWT_AUDIENCE = "billing-support-web"


def _make_jwt(email: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": email, "role": role, "iat": now, "exp": now + timedelta(days=JWT_EXPIRE_DAYS),
         "iss": JWT_ISSUER, "aud": JWT_AUDIENCE},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def _password_bytes(password: str) -> bytes:
    """bcrypt reads at most 72 bytes and bcrypt 5 raises past that; one character can be up to 4 bytes."""
    return password.encode("utf-8")


def _normalise_email(email: str) -> str:
    email = email.strip().lower()
    if not _EMAIL.match(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    return email


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UserOut:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM],
                             audience=JWT_AUDIENCE, issuer=JWT_ISSUER,
                             options={"require": ["exp", "sub", "iss", "aud"]})
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session -- please sign in again")
    email: str = payload.get("sub", "")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    # The database is the source of truth for role and status, so disabling or demoting a user takes effect
    # on their next request instead of when the token expires. A token whose user row was deleted is refused:
    # the role claim inside it is never trusted on its own.
    with get_db() as conn:
        row = conn.execute("SELECT role, is_active FROM users WHERE lower(email)=lower(?)", (email,)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session -- please sign in again")
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="This account has been disabled")
    return UserOut(email=email, role=row["role"])


def require_admin(user: UserOut = Depends(get_current_user)) -> UserOut:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/config", response_model=AuthConfig)
def auth_config() -> AuthConfig:
    """What the login page may offer. Public."""
    return AuthConfig(google_client_id=GOOGLE_CLIENT_ID, password_auth_enabled=PASSWORD_AUTH_ENABLED)


@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("5/minute")
def register(request: Request, body: RegisterRequest) -> TokenResponse:
    if not PASSWORD_AUTH_ENABLED:
        raise HTTPException(status_code=404, detail="Password sign-up is disabled")
    email = _normalise_email(body.email)
    full_name = body.full_name.strip()
    if not full_name:
        raise HTTPException(status_code=422, detail="Enter your full name")
    password = _password_bytes(body.password)
    if len(password) > 72:
        raise HTTPException(status_code=422, detail="Password is too long: use at most 72 bytes (fewer if it has accented or non-Latin characters)")
    if email == ADMIN_EMAIL.lower():
        # The admin account is claimed only through Google, which proves the address is theirs.
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    hashed = bcrypt.hashpw(password, bcrypt.gensalt()).decode("ascii")
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM users WHERE lower(email)=?", (email,)).fetchone():
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        conn.execute(
            "INSERT INTO users (email, role, password_hash, full_name, auth_provider) VALUES (?,?,?,?,?)",
            (email, "user", hashed, full_name, "password"),
        )
    from api.billing import repo
    repo.audit(email, "signup", email, {"provider": "password"})
    return TokenResponse(token=_make_jwt(email, "user"), user=UserOut(email=email, role="user"))


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def password_login(request: Request, body: PasswordLoginRequest) -> TokenResponse:
    if not PASSWORD_AUTH_ENABLED:
        raise HTTPException(status_code=404, detail="Password sign-in is disabled")
    email = body.email.strip().lower()
    if _too_many_failures(email):
        raise HTTPException(status_code=429, detail="Too many failed attempts. Wait 15 minutes, then try again.")
    with get_db() as conn:
        row = conn.execute("SELECT email, role, password_hash, is_active FROM users WHERE lower(email)=?",
                           (email,)).fetchone()
    stored = row["password_hash"].encode("ascii") if row and row["password_hash"] else _DUMMY_HASH
    password = _password_bytes(body.password)
    # No stored password is longer than 72 bytes, so a longer one cannot match; still pay for one check.
    ok = bcrypt.checkpw(password, stored) if len(password) <= 72 else (bcrypt.checkpw(b"x", _DUMMY_HASH) and False)
    if not (row and row["password_hash"] and ok):
        _record_failure(email)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="This account has been disabled")
    with _failed_lock:
        _failed.pop(email, None)
    return TokenResponse(token=_make_jwt(row["email"], row["role"]),
                         user=UserOut(email=row["email"], role=row["role"]))


@router.post("/google", response_model=TokenResponse)
@limiter.limit("10/minute")
def google_login(request: Request, body: GoogleLoginRequest) -> TokenResponse:
    """Verify a Google ID token and return an app JWT."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=404, detail="Google sign-in is not configured")
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
        idinfo = google_id_token.verify_oauth2_token(
            body.credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except ValueError:
        # Deliberately vague: do not leak internal verification details
        raise HTTPException(status_code=401, detail="Google sign-in failed: invalid credential")

    email: str = (idinfo.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="Google account has no email address")
    if idinfo.get("email_verified") is not True:
        raise HTTPException(status_code=401, detail="Verify this email address with Google, then sign in again")

    created = False
    with get_db() as conn:
        row = conn.execute("SELECT role, is_active FROM users WHERE lower(email) = ?", (email,)).fetchone()
        if row:
            role: str = row["role"]
            if not row["is_active"]:
                raise HTTPException(status_code=403, detail="This account has been disabled")
        else:
            role = "admin" if email == ADMIN_EMAIL.lower() else "user"
            conn.execute("INSERT INTO users (email, role, full_name, auth_provider) VALUES (?,?,?,?)",
                         (email, role, idinfo.get("name", ""), "google"))
            created = True
    if created:
        from api.billing import repo
        repo.audit(email, "signup", email, {"provider": "google"})

    return TokenResponse(token=_make_jwt(email, role), user=UserOut(email=email, role=role))


@router.get("/me", response_model=MeOut)
def me(user: UserOut = Depends(get_current_user)) -> MeOut:
    from api.billing import repo
    row = repo.get_user_by_email(user.email)
    sub = repo.current_subscription(row["id"]) if row else None
    return MeOut(email=user.email, role=user.role, full_name=(row or {}).get("full_name", "") or "",
                 auth_provider=(row or {}).get("auth_provider", "google"),
                 onboarded=bool(sub and sub["status"] != "cancelled"))

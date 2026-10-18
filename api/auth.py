"""Authentication: email + password accounts and Google sign-in, both issuing the same JWT session token."""

import re
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
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

def _make_jwt(email: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": email, "role": role, "exp": expire},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


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
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session — please sign in again")
    email: str = payload.get("sub", "")
    role: str = payload.get("role", "user")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    # The database is the source of truth for role and status, so disabling or demoting a user takes effect
    # on their next request instead of when the token expires. A token for an email with no row keeps its
    # own claims (tokens are only ever issued for existing rows).
    with get_db() as conn:
        row = conn.execute("SELECT role, is_active FROM users WHERE lower(email)=lower(?)", (email,)).fetchone()
    if row is not None:
        if not row["is_active"]:
            raise HTTPException(status_code=403, detail="This account has been disabled")
        role = row["role"]
    return UserOut(email=email, role=role)


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
    if email == ADMIN_EMAIL.lower():
        # The admin account is claimed only through Google, which proves the address is theirs.
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    hashed = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
    with get_db() as conn:
        if conn.execute("SELECT 1 FROM users WHERE lower(email)=?", (email,)).fetchone():
            raise HTTPException(status_code=409, detail="An account with this email already exists")
        conn.execute(
            "INSERT INTO users (email, role, password_hash, full_name, auth_provider) VALUES (?,?,?,?,?)",
            (email, "user", hashed, body.full_name.strip(), "password"),
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
    with get_db() as conn:
        row = conn.execute("SELECT email, role, password_hash, is_active FROM users WHERE lower(email)=?",
                           (email,)).fetchone()
    stored = row["password_hash"].encode("ascii") if row and row["password_hash"] else _DUMMY_HASH
    ok = bcrypt.checkpw(body.password.encode("utf-8"), stored)
    if not (row and row["password_hash"] and ok):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="This account has been disabled")
    return TokenResponse(token=_make_jwt(row["email"], row["role"]),
                         user=UserOut(email=row["email"], role=row["role"]))


@router.post("/google", response_model=TokenResponse)
def google_login(body: GoogleLoginRequest) -> TokenResponse:
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
        # Deliberately vague — do not leak internal verification details
        raise HTTPException(status_code=401, detail="Google sign-in failed — invalid credential")

    email: str = idinfo.get("email", "")
    if not email:
        raise HTTPException(status_code=401, detail="Google account has no email address")

    created = False
    with get_db() as conn:
        row = conn.execute("SELECT role, is_active FROM users WHERE email = ?", (email,)).fetchone()
        if row:
            role: str = row["role"]
            if not row["is_active"]:
                raise HTTPException(status_code=403, detail="This account has been disabled")
        else:
            role = "admin" if email == ADMIN_EMAIL else "user"
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

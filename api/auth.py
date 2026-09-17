"""Authentication — Google OAuth2 verification + JWT session tokens."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from api.config import ADMIN_EMAIL, GOOGLE_CLIENT_ID, JWT_ALGORITHM, JWT_EXPIRE_DAYS, JWT_SECRET
from api.database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GoogleLoginRequest(BaseModel):
    credential: str


class UserOut(BaseModel):
    email: str
    role: str


class TokenResponse(BaseModel):
    token: str
    user: UserOut


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
        email: str = payload.get("sub", "")
        role: str = payload.get("role", "user")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return UserOut(email=email, role=role)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session — please sign in again")


def require_admin(user: UserOut = Depends(get_current_user)) -> UserOut:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/google", response_model=TokenResponse)
def google_login(body: GoogleLoginRequest) -> TokenResponse:
    """Verify a Google ID token and return an app JWT."""
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

    with get_db() as conn:
        row = conn.execute("SELECT role FROM users WHERE email = ?", (email,)).fetchone()
        if row:
            role: str = row["role"]
        else:
            role = "admin" if email == ADMIN_EMAIL else "user"
            conn.execute("INSERT INTO users (email, role) VALUES (?,?)", (email, role))

    return TokenResponse(token=_make_jwt(email, role), user=UserOut(email=email, role=role))


@router.get("/me", response_model=UserOut)
def me(user: UserOut = Depends(get_current_user)) -> UserOut:
    return user

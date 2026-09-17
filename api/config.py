"""Centralised application configuration loaded from environment / .env file."""

import os
import sys
from pathlib import Path

# Ensure .env is loaded before any settings are read
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
except ImportError:
    pass


def _require(name: str) -> str:
    """Return the value of a required environment variable, aborting on startup if missing."""
    val = os.getenv(name, "").strip()
    if not val:
        print(f"[FATAL] Environment variable {name!r} is required but not set. "
              f"Copy .env.example to .env and fill in the value.", file=sys.stderr)
        sys.exit(1)
    return val


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
GOOGLE_CLIENT_ID: str = _require("GOOGLE_CLIENT_ID")
JWT_SECRET: str = _require("JWT_SECRET")
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRE_DAYS: int = 7

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
ADMIN_EMAIL: str = _get("ADMIN_EMAIL", "essvaransekar2410@gmail.com")

# ---------------------------------------------------------------------------
# CORS  —  comma-separated origins, e.g.  http://localhost:4200,https://app.example.com
# ---------------------------------------------------------------------------
_raw_origins = _get("ALLOWED_ORIGINS", "http://localhost:4200")
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
MAX_UPLOAD_BYTES: int = int(_get("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))  # 20 MB

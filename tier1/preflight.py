"""Configuration and readiness checks shared by `python -m tier1 up` and the API's startup and /api/ready.

Every check returns a Problem with a plain-language fix, so a stranger reading the output knows what to do next.
Nothing here prints secrets: values are only tested for presence, length and leftover placeholders.
"""
import os
from dataclasses import dataclass

from src.config import CHROMA_DB_DIR, PROJECT_ROOT, TIER1_COLLECTION, VARIANT_A_DIR

ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
PLACEHOLDERS = ("your_", "change_me", "change-me", "changeme", "replace_me", "xxx")
MIN_SECRET_CHARS = 32


@dataclass
class Problem:
    level: str      # "error" stops startup in production; "warning" is reported and allowed
    key: str
    message: str
    fix: str

    def as_dict(self) -> dict:
        return {"level": self.level, "key": self.key, "message": self.message, "fix": self.fix}


def app_env() -> str:
    return os.getenv("APP_ENV", "development").strip().lower() or "development"


def is_production() -> bool:
    return app_env() == "production"


def _placeholder(value: str) -> bool:
    v = value.strip().lower()
    return not v or any(p in v for p in PLACEHOLDERS)


def check_env() -> list[Problem]:
    """Environment variables. Call after .env has been loaded."""
    out: list[Problem] = []
    if _placeholder(os.getenv("GROQ_API_KEY", "")):
        out.append(Problem("error", "GROQ_API_KEY", "No model provider key is set, so no ticket can be answered.",
                           "Create a free key at https://console.groq.com/keys and put it in .env as GROQ_API_KEY=..."))
    secret = os.getenv("JWT_SECRET", "")
    if _placeholder(secret):
        out.append(Problem("error", "JWT_SECRET", "The sign-in secret is missing or still the example value.",
                           "Set JWT_SECRET in .env to a long random string, for example the output of: "
                           "python -c \"import secrets; print(secrets.token_urlsafe(48))\""))
    elif len(secret) < MIN_SECRET_CHARS:
        out.append(Problem("error" if is_production() else "warning", "JWT_SECRET",
                           f"The sign-in secret is shorter than {MIN_SECRET_CHARS} characters, which makes tokens guessable.",
                           "Use a random string of at least 32 characters."))
    if _placeholder(os.getenv("ADMIN_EMAIL", "")):
        out.append(Problem("error", "ADMIN_EMAIL", "No team lead account is configured, so nobody can reach the admin pages.",
                           "Set ADMIN_EMAIL in .env to the email the team lead signs in with."))
    if is_production():
        if os.getenv("LLM_CACHE", "readwrite").strip().lower() != "off":
            out.append(Problem("error", "LLM_CACHE", "The response cache keeps full prompts (customer text) on disk.",
                               "Set LLM_CACHE=off in production."))
        if os.getenv("TIER1_DEMO_CUSTOMER_ID", "").strip():
            out.append(Problem("error", "TIER1_DEMO_CUSTOMER_ID",
                               "Every signed-in user would act as the same demo customer.",
                               "Remove TIER1_DEMO_CUSTOMER_ID in production; users are matched to customers by email."))
        if _placeholder(os.getenv("PII_HASH_SALT", "")):
            out.append(Problem("error", "PII_HASH_SALT", "Hashed customer ids in traces use the public example salt.",
                               "Set PII_HASH_SALT in .env to a private random string."))
    return out


def check_data() -> list[Problem]:
    out: list[Problem] = []
    if not (VARIANT_A_DIR / "customers.json").exists():
        out.append(Problem("error", "corpus", "The synthetic help centre and customers have not been generated.",
                           "Run: python -m tier1 up   (or: python scripts/generate_synthetic_corpus.py)"))
    if collection_size() == 0:
        out.append(Problem("error", "search_index", "The help-centre search index is empty or missing.",
                           "Run: python -m tier1 up   (or: python scripts/ingest_variant_a.py)"))
    return out


def collection_size() -> int:
    if not CHROMA_DB_DIR.exists():
        return 0
    try:
        from src.retrieval.vector_store import get_client
        return get_client().get_collection(TIER1_COLLECTION).count()
    except Exception:
        return 0


def available_models(timeout: float = 15.0) -> list[str] | None:
    """Model ids the key can reach (one free request), or None if the provider could not be asked."""
    key = os.getenv("GROQ_API_KEY", "")
    if _placeholder(key):
        return None
    try:
        import httpx
        r = httpx.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
    except Exception:
        return None
    if r.status_code == 401:
        return []
    if r.status_code != 200:
        return None
    return sorted(m["id"] for m in r.json().get("data", []))


def check_models(models: list[str] | None) -> list[Problem]:
    if models is None:
        return [Problem("warning", "provider", "Could not reach the model provider to check the key.",
                        "Check your internet connection; answers will fail until the provider is reachable.")]
    if not models:
        return [Problem("error", "GROQ_API_KEY", "The provider rejected the key (401).",
                        "Copy the key again from https://console.groq.com/keys into .env.")]
    out = []
    from src.catalog import settings
    agent, judge = settings.get("models.agent"), settings.get("models.judge")
    if agent not in models:
        out.append(Problem("error", "LLM_MODEL", f"Your key cannot use the agent model {agent}.",
                           "Change Admin, Settings, Tier-1 agent model (or LLM_MODEL in .env) to one of: " + ", ".join(m for m in models if "gpt-oss" in m or "qwen" in m)))
    if judge not in models:
        out.append(Problem("warning", "JUDGE_MODEL", f"Your key cannot use the judge model {judge}; the eval judge will fail.",
                           "Change Admin, Settings, Eval judge model (or JUDGE_MODEL in .env) to a model from another family."))
    return out

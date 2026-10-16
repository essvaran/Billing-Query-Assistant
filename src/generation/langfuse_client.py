import os

from dotenv import load_dotenv

load_dotenv()

_langfuse = None


def _init() -> None:
    global _langfuse
    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    sk = os.getenv("LANGFUSE_SECRET_KEY", "")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if not pk or not sk or pk == "your_public_key_here":
        return

    # Requires langfuse 2.x — in v2, langfuse.Langfuse is the high-level SDK
    # with .trace() / .span() / .generation(). v3 restructured to a Fern-generated
    # REST client and removed this API entirely.
    try:
        from langfuse import Langfuse
        client = Langfuse(public_key=pk, secret_key=sk, host=host)
        if not callable(getattr(client, "trace", None)):
            return  # guard: wrong class, bail silently
        _langfuse = client
    except Exception:
        pass


_init()


def get_langfuse():
    return _langfuse


def host():
    return os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com").strip().rstrip("/")


def trace_url(trace_id):
    """Link to a trace in Langfuse, or None when Langfuse is not configured."""
    if _langfuse is None or not trace_id:
        return None
    return f"{host()}/trace/{trace_id}"


def score_feedback(trace_id, score_key, rating, reason_code=None, comment=None):
    """Attach user feedback to the Langfuse trace as scores. Returns True if queued.

    score_key makes the score id stable per (trace, user), so changing a vote updates the
    same score instead of adding a second one.
    """
    lf = _langfuse
    if lf is None:
        return False
    detail = " / ".join(part for part in (reason_code, comment) if part) or None
    try:
        lf.score(
            id=f"fb-{score_key}",
            trace_id=trace_id,
            name="user-feedback",
            value=1 if rating == "up" else 0,
            data_type="BOOLEAN",
            comment=detail,
        )
        if rating == "down" and reason_code:
            lf.score(
                id=f"fbr-{score_key}",
                trace_id=trace_id,
                name="user-feedback-reason",
                value=reason_code,
                data_type="CATEGORICAL",
                comment=comment or None,
            )
        lf.flush()
        return True
    except Exception:
        return False

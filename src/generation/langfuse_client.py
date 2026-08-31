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

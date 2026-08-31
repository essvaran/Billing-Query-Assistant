import importlib.metadata
import sys

# 1. Check version
try:
    v = importlib.metadata.version("langfuse")
    print(f"langfuse version: {v}")
    if not v.startswith("2."):
        print("WRONG VERSION — run: pip install 'langfuse>=2,<3'")
        sys.exit(1)
except Exception as e:
    print(f"langfuse not installed: {e}")
    sys.exit(1)

# 2. Check our client initialises
from src.generation.langfuse_client import get_langfuse
lf = get_langfuse()
print(f"LangFuse client: {lf}")
print(f"Has .trace: {callable(getattr(lf, 'trace', None))}")

if lf is None:
    print("CLIENT IS NONE — keys missing or wrong in .env")
    sys.exit(1)

# 3. Send a real test trace and flush
t = lf.trace(name="debug-ping", input={"test": True})
lf.flush()
print(f"Trace sent! ID: {t.id}")
print("Check LangFuse dashboard → Tracing in ~5 seconds.")

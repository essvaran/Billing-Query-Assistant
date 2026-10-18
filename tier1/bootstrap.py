"""`python -m tier1 up`: one command from a fresh clone to a first answered ticket.

Each stage prints OK, SKIP (already done) or FAIL with the exact fix, and every stage is safe to repeat: a second run
skips whatever the first one finished. It never prints a secret.
"""
import importlib
import shutil
import subprocess
import sys
import time

from src.config import PROJECT_ROOT, VARIANT_A_DIR
from tier1 import preflight

REQUIRED_IMPORTS = ("fastapi", "chromadb", "sentence_transformers", "mcp", "httpx", "langchain_text_splitters")


def _say(status: str, stage: str, detail: str = "") -> None:
    print(f"[{status:<4}] {stage}" + (f": {detail}" if detail else ""), flush=True)


def _fail(stage: str, problems: list) -> int:
    _say("FAIL", stage)
    for p in problems:
        print(f"        - {p.message}\n          Fix: {p.fix}")
    print("\nFix the items above, then run the same command again. Finished stages are skipped.")
    return 1


def _run(cmd: list[str]) -> bool:
    return subprocess.run(cmd, cwd=str(PROJECT_ROOT)).returncode == 0


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m tier1 up", description="Set up everything and answer one ticket")
    ap.add_argument("--no-install", action="store_true", help="never run pip; just report missing packages")
    ap.add_argument("--no-demo", action="store_true", help="stop after setup, without answering a ticket")
    args = ap.parse_args(argv)
    started = time.monotonic()
    print("Tier-1 Deflection Assistant: setup\n")

    # 1. Python
    if sys.version_info < (3, 11):
        return _fail("Python", [preflight.Problem("error", "python", f"Python {sys.version.split()[0]} is too old.",
                                                  "Install Python 3.12 and create the virtual environment with it.")])
    _say("OK", "Python", sys.version.split()[0] + ("" if sys.version_info[:2] == (3, 12) else " (3.12 is the tested version)"))

    # 2. .env
    if not preflight.ENV_FILE.exists():
        shutil.copyfile(preflight.ENV_EXAMPLE, preflight.ENV_FILE)
        _say("FAIL", ".env", "created from .env.example; it needs your values")
        print("        Open .env and fill in GROQ_API_KEY, JWT_SECRET and ADMIN_EMAIL, then run this command again.")
        return 1
    from dotenv import load_dotenv
    load_dotenv(preflight.ENV_FILE, override=False)
    problems = preflight.check_env()
    errors = [p for p in problems if p.level == "error"]
    if errors:
        return _fail(".env", errors)
    _say("OK", ".env", f"APP_ENV={preflight.app_env()}")
    for p in problems:
        _say("WARN", p.key, f"{p.message} {p.fix}")

    # 3. packages
    missing = []
    for name in REQUIRED_IMPORTS:
        try:
            importlib.import_module(name)
        except ImportError:
            missing.append(name)
    if missing:
        if args.no_install:
            return _fail("packages", [preflight.Problem("error", "packages", f"Missing: {', '.join(missing)}",
                                                        "Run: python -m pip install -r requirements.txt")])
        _say("....", "packages", f"installing (missing {', '.join(missing)}); this takes a few minutes the first time")
        if not _run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]):
            return _fail("packages", [preflight.Problem("error", "packages", "pip install failed (see its output above).",
                                                        "Fix the pip error, then run this command again.")])
        _say("OK", "packages", "installed")
    else:
        _say("SKIP", "packages", "already installed")

    # 4. provider key and models (one free request)
    model_problems = preflight.check_models(preflight.available_models())
    if any(p.level == "error" for p in model_problems):
        return _fail("model provider", [p for p in model_problems if p.level == "error"])
    _say("OK", "model provider", "key accepted, agent model available")
    for p in model_problems:
        _say("WARN", p.key, f"{p.message} {p.fix}")

    # 5. synthetic corpus, customers, orders, tickets (deterministic)
    if (VARIANT_A_DIR / "customers.json").exists():
        _say("SKIP", "synthetic data", "already generated")
    elif _run([sys.executable, "scripts/generate_synthetic_corpus.py"]):
        _say("OK", "synthetic data", "generated")
    else:
        return _fail("synthetic data", [preflight.Problem("error", "corpus", "The generator failed (see above).",
                                                          "Run: python scripts/generate_synthetic_corpus.py")])

    # 6. search index
    if preflight.collection_size():
        _say("SKIP", "search index", f"{preflight.collection_size()} chunks already indexed")
    else:
        _say("....", "search index", "building; the first run downloads the embedding model (about 400 MB)")
        if not _run([sys.executable, "scripts/ingest_variant_a.py"]) or not preflight.collection_size():
            return _fail("search index", [preflight.Problem("error", "search_index", "Indexing failed (see above).",
                                                            "Run: python scripts/ingest_variant_a.py")])
        _say("OK", "search index", f"{preflight.collection_size()} chunks")

    # 7. ticket database
    from tier1 import db
    seeded = db.seed_from_synthetic()
    with db.get_conn() as conn:
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("customers", "orders", "tickets")}
    _say("OK" if seeded.get("seeded", True) else "SKIP", "ticket database",
         f"{counts['customers']} customers, {counts['orders']} orders, {counts['tickets']} tickets"
         + ("" if seeded.get("seeded", True) else " (already loaded)"))
    from src.catalog import db as catalog_db, ref as catalog_ref
    catalog_db.ensure()
    _say("OK", "catalog", f"{len(catalog_ref.all_categories())} reference lists, settings, prices, prompts and guard rules in {catalog_db.DB_PATH.name}")

    # 8. one real ticket through the whole system
    if not args.no_demo:
        _say("....", "first ticket", "answering a random sample ticket (the first one starts the tool servers, about 15 s)")
        from tier1.__main__ import main as cli
        code = cli(["demo"])
        if code != 0:
            return _fail("first ticket", [preflight.Problem("error", "demo", "The sample ticket could not be answered.",
                                                            "Read the error above; python -m tier1 demo repeats this step.")])
        _say("OK", "first ticket")

    print(f"\nReady in {time.monotonic() - started:.0f} s. Next:\n"
          "  python -m tier1 demo                  answer another random ticket\n"
          "  make api   (Windows: ./tasks.ps1 api)  start the API on http://localhost:8000\n"
          "  cd frontend && npm ci && npx ng serve --proxy-config proxy.conf.json   the web app on http://localhost:4200\n"
          "  FUNCTIONAL_README.md                  what each role can do, step by step (README.md: technical)")
    return 0

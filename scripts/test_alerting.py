"""Send one test alert through the real SMTP path to verify ALERT_* config.

Usage:
    python scripts/test_alerting.py            # sends an email (needs ALERT_* in .env)
    python scripts/test_alerting.py --dry-run  # only evaluates conditions, sends nothing
"""
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv()

from src.observability.alerting import evaluate_conditions, send_alert_email

SAMPLE = {
    "trace_id": "test-trace",
    "timestamp": "2026-10-12T00:00:00+00:00",
    "question": "Can I get a refund if my billing migration fails?",
    "final_answer": "Yes, you are entitled to a full refund within 30 days.",
    "citations_valid": False,
    "cost_usd": 0.0,
    "total_ms": 1000,
    "prompt_version": "v1",
    "error": None,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    alerts = evaluate_conditions(SAMPLE)
    print("conditions tripped:", [a[0] for a in alerts])
    if args.dry_run:
        return
    send_alert_email("[RAG Alert] test - trace test-trace", f"Test alert.\n{SAMPLE}")
    print("email sent")


if __name__ == "__main__":
    main()

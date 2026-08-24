"""Generate a diverse trace file by running questions through the RAG pipeline.

Each of the 20 questions is run once with the hybrid BM25+RRF retriever,
producing 20 trace records in evaluation/traces.jsonl (gitignored).

Usage:
    python scripts/generate_traces.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.generation.answer import answer_question

DELAY_SECONDS = 5  # pause between requests to stay within Groq rate limits

QUESTIONS = [
    # ── Error code lookups (exact) ────────────────────────────────────────────
    "What does ERR-4032 mean?",
    "What causes PAY-1001?",
    "What does ERR-5010 mean?",
    "What does ERR-4040 mean?",
    "What does ERR-6030 mean?",
    "What does ERR-6001 mean?",
    "What causes PAY-1002?",
    "What causes PAY-1003?",
    "What causes PAY-1006?",
    "What causes PAY-1007?",
    "What causes PAY-1011?",
    "What causes PAY-1012?",
    "What does DAT-6001 mean?",
    "What does INV-2001 mean?",

    # ── Error code lookups (paraphrased) ─────────────────────────────────────
    "I'm seeing ERR-4032 during migration, what happened?",
    "My billing migration shows ERR-5010 — what does that mean?",
    "Error code ERR-4040 appeared, how do I fix it?",
    "ERR-6030 is blocking my rollback request",
    "The migration is stuck with error 4032",
    "I have a billing profile migration incomplete error",
    "My invoice account appears to be locked because of a dispute",
    "Payment method re-verification failed during migration",
    "Getting a rollback error with code 6030",
    "The card network token exchange failed",
    "Checksum mismatch error appeared during migration",
    "Invoice record shows inconsistent state error",
    "Legacy plan ID has no mapping to new platform",
    "Tax platform API key error during migration sync",
    "Default payment method expired before migration completed",

    # ── Exact identifier stress ───────────────────────────────────────────────
    "What does PLAN-ENT-V1 map to on the new platform?",
    "What does SUB-4001 indicate?",
    "What is PLAN-ENT-V1?",
    "Tell me about PLAN-ENT-V1 subscription mapping",
    "What is PAY-1001 and how do I fix it?",
    "What is PAY-1012?",
    "What is DAT-6001 and when does it occur?",
    "What is INV-2001?",
    "Explain ERR-6001 and when it happens",
    "What is SYNC-9005?",
    "What is SYNC-9006?",
    "Tell me about PAY-1007",
    "PAY-1011 error — what happened?",

    # ── Procedural — step-by-step ────────────────────────────────────────────
    "How do I request a migration rollback?",
    "What do I do if the same migration step fails three times?",
    "What steps do I take to confirm a billing migration?",
    "How do I add a new payment method during migration?",
    "How do I set a default payment method?",
    "What is the process for escalating to billing support?",
    "How do I retry a failed migration?",
    "How do I access the Billing Overview page?",
    "How do I submit a billing dispute after migration?",
    "How do I update my card expiry?",
    "How do I reconnect a billing profile?",
    "What should I do when migration fails on the same step three times?",

    # ── Permission / role queries ─────────────────────────────────────────────
    "Which account roles can confirm a billing migration?",
    "Can a Finance Viewer confirm migration?",
    "Can a Member role request a rollback?",
    "Who can initiate a billing migration?",
    "What can a Billing Administrator do during migration?",
    "Can I add a Billing Administrator while migration is in progress?",
    "What is the difference between Account Owner and Billing Administrator during migration?",
    "Who is allowed to submit a rollback request?",
    "Can Finance Viewer see the migration status?",
    "What permissions does the Member role have during migration?",

    # ── Out-of-corpus (should trigger refusal) ───────────────────────────────
    "Can I get a refund if my billing migration fails?",
    "What is the processing fee for international credit card payments?",
    "How long is the cancellation window after migration?",
    "What is the SLA for billing support response time?",
    "Do you offer a free trial after migration?",
    "What is the penalty for late invoice payment?",
    "How do I cancel my subscription after migrating?",
    "What is the refund policy for unused subscription days?",
    "Are there discounts available after migration?",
    "What currencies are supported for billing?",

    # ── Multi-part questions ──────────────────────────────────────────────────
    "How do I fix ERR-4040 and what happens to auto-pay after migration?",
    "What is ERR-6030 and who can submit a rollback request?",
    "What is ERR-4032 and how long does it take to resolve?",
    "Who can confirm migration and what do they need to do?",
    "What happens to auto-pay during migration and how do I re-enable it?",
    "Can a completed migration be rolled back and what are the error codes related to rollback?",
    "What does PAY-1001 mean and how do I add a new payment method?",
    "How do I request a rollback and what are the time limits?",
    "What migration errors are blocking and which ones are not?",
    "What roles can do billing migration tasks and what can each role do?",

    # ── Ambiguous / vague ────────────────────────────────────────────────────
    "My migration is stuck, what do I do?",
    "The billing page shows an error",
    "Migration failed, help",
    "It won't let me migrate",
    "I can't access billing",
    "The payment method isn't working",
    "Migration keeps failing",
    "Billing error on my account",
    "Something went wrong during migration",
    "My account is locked",

    # ── Policy / condition queries ────────────────────────────────────────────
    "When can a billing migration rollback not happen?",
    "What happens to invoice history after migration?",
    "What triggers the auto-pay pause during migration?",
    "Under what conditions is a rollback possible?",
    "What data moves during a billing profile migration?",
    "Are retries rate-limited during migration?",
    "What happens to credits and subscription terms during migration?",
    "When does migration reach completed status?",
    "What invoice and payment data is preserved after migration?",
    "What happens to card details during migration?",

    # ── Follow-up style ───────────────────────────────────────────────────────
    "What if the same migration step fails three times in a row?",
    "What happens after I request a rollback?",
    "After adding a new payment method, what do I do next?",
    "What if my rollback request is denied?",
    "How do I know if auto-pay has resumed after migration?",
    "What if I can't find the 'Request rollback' option?",
]


def main() -> None:
    total = len(QUESTIONS)
    print(f"Running {total} questions with hybrid BM25+RRF retriever")
    print(f"Output: evaluation/traces.jsonl")
    print(f"Delay between requests: {DELAY_SECONDS}s  (estimated time: ~{total * DELAY_SECONDS // 60} min)\n")

    count = 0
    for i, question in enumerate(QUESTIONS, 1):
        try:
            answer_question(question, use_hybrid=True)
            count += 1
        except Exception as exc:
            print(f"  ERROR Q{i}: {exc}")

        pct = i / total * 100
        print(f"  [{i:3d}/{total}] {pct:5.1f}%  {question[:60]}")

        if i < total:
            time.sleep(DELAY_SECONDS)

    print(f"\nDone. {count} traces written.")


if __name__ == "__main__":
    main()

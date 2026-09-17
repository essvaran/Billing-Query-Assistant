"""Fixed 3-step workflow for refund-chase ticket resolution.

No agent loop -- hard-codes the same tool calls in a deterministic sequence
and makes exactly one LLM call to draft the reply. Same tools, same model,
same output contract as the agent loop.

Langfuse traces every run: one trace, three tool spans, one generation.

Run a single ticket:
    python -m agent.workflow T001
"""

import os
import sys
import time
from dataclasses import dataclass

from dotenv import load_dotenv

from agent.tools import get_ticket, get_order, get_customer_tier
from agent.tickets import score_reply
from src.generation.llm_client import ask_llm

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

COST_PER_1M_TOKENS = 0.90  # USD per 1M tokens
MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
_LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")).rstrip("/")

SYSTEM_PROMPT = (
    "You are a billing support agent. Draft a concise refund reply based on the "
    "information provided.\n"
    "- Approve the refund if days_since_purchase is within the customer's refund_days window.\n"
    "- Deny the refund if outside the window.\n"
    "- Escalate (instruct the customer to email billing@company.com) if the order record "
    "cannot be found."
)


@dataclass
class WorkflowResult:
    ticket_id: str
    reply: str
    total_tokens: int
    cost_usd: float
    latency_s: float
    passed: bool
    order_missing: bool = False
    trace_id: str | None = None
    trace_url: str | None = None


def run_workflow(
    ticket_id: str,
    expected_verdict: str | None = None,
    verbose: bool = False,
) -> WorkflowResult:
    t_start = time.monotonic()

    # --- Langfuse setup ---
    try:
        from src.generation.langfuse_client import get_langfuse
        lf = get_langfuse()
    except Exception:
        lf = None

    lf_trace = None
    if lf:
        try:
            from agent.tickets import TICKETS
            ticket_text = TICKETS.get(ticket_id, {}).get("text", "")
            lf_trace = lf.trace(
                name="workflow_run",
                input={"ticket_id": ticket_id, "ticket_text": ticket_text},
                tags=["workflow", "week7-task-a"],
                metadata={
                    "system": "workflow",
                    "model": MODEL,
                    "expected_verdict": expected_verdict,
                },
            )
        except Exception:
            lf_trace = None

    def _span_start(name: str, input_data: dict):
        if lf_trace:
            try:
                return lf_trace.span(name=name, input=input_data)
            except Exception:
                pass
        return None

    def _span_end(span, output_data: dict):
        if span:
            try:
                span.end(output=output_data)
            except Exception:
                pass

    # Step 1 -- always get the ticket
    s1 = _span_start("step_1_get_ticket", {"ticket_id": ticket_id})
    ticket = get_ticket(ticket_id)
    _span_end(s1, ticket)

    if "error" in ticket:
        latency = time.monotonic() - t_start
        reply = "We could not locate that support ticket. Please contact support@company.com."
        if verbose:
            print("  [step 1] ticket not found", flush=True)

        trace_id, trace_url = _finalize_trace(lf, lf_trace, {
            "reply": reply, "passed": False, "order_missing": False,
        }, {"total_tokens": 0, "cost_usd": 0.0, "latency_s": round(latency, 3)})

        return WorkflowResult(
            ticket_id=ticket_id, reply=reply, total_tokens=0, cost_usd=0.0,
            latency_s=latency, passed=score_reply(reply, expected_verdict),
            trace_id=trace_id, trace_url=trace_url,
        )

    if verbose:
        print(
            f"  [step 1] ticket={ticket['ticket_id']} "
            f"order_id={ticket['order_id']} customer_id={ticket['customer_id']}",
            flush=True,
        )

    # Step 2 -- always get the order
    s2 = _span_start("step_2_get_order", {"order_id": ticket["order_id"]})
    order = get_order(ticket["order_id"])
    _span_end(s2, order)

    order_missing = "error" in order
    if verbose:
        if order_missing:
            print(f"  [step 2] order={ticket['order_id']} MISSING", flush=True)
        else:
            print(
                f"  [step 2] order={order['order_id']} "
                f"days={order['days_since_purchase']} amount=${order['amount_usd']:.2f}",
                flush=True,
            )

    # Step 3 -- always get customer tier
    s3 = _span_start("step_3_get_customer_tier", {"customer_id": ticket["customer_id"], "tier": "standard"})
    tier_info = get_customer_tier(ticket["customer_id"], tier="standard")
    _span_end(s3, tier_info)

    if verbose:
        print(
            f"  [step 3] tier={tier_info.get('tier')} "
            f"refund_days={tier_info.get('refund_days')}",
            flush=True,
        )

    # Build the LLM prompt with all gathered facts
    if order_missing:
        order_context = f"Order {ticket['order_id']}: NOT FOUND in the system."
    else:
        order_context = (
            f"Order {order['order_id']}: purchased {order['purchase_date']} "
            f"({order['days_since_purchase']} days ago), amount ${order['amount_usd']:.2f}, "
            f"status: {order['status']}."
        )

    user_prompt = (
        f"Ticket {ticket_id}: \"{ticket['text']}\"\n\n"
        f"{order_context}\n"
        f"Customer tier: {tier_info.get('tier', 'unknown')} "
        f"(refund window: {tier_info.get('refund_days', 30)} days).\n\n"
        f"Draft the refund reply now."
    )

    # Single LLM call -- trace as a generation on the trace (not inside a lap span)
    lf_gen = None
    if lf_trace:
        try:
            lf_gen = lf_trace.generation(
                name="llm_call",
                model=MODEL,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                metadata={"temperature": 0.0, "order_missing": order_missing},
            )
        except Exception:
            lf_gen = None

    text, in_tok, out_tok = ask_llm(SYSTEM_PROMPT, user_prompt)

    if lf_gen:
        try:
            lf_gen.end(
                output=text,
                usage={"input": in_tok, "output": out_tok, "unit": "TOKENS"},
            )
        except Exception:
            pass

    total_tokens = in_tok + out_tok
    cost = (total_tokens / 1_000_000) * COST_PER_1M_TOKENS
    latency = time.monotonic() - t_start
    passed = score_reply(text, expected_verdict)

    if verbose:
        print(f"  [llm] in={in_tok} out={out_tok} total={total_tokens} latency={latency:.2f}s", flush=True)
        print(f"  Reply: {text[:200]}", flush=True)

    trace_id, trace_url = _finalize_trace(lf, lf_trace, {
        "reply": text, "passed": passed, "verdict": expected_verdict,
    }, {
        "total_tokens": total_tokens, "cost_usd": round(cost, 6),
        "latency_s": round(latency, 3), "order_missing": order_missing,
    })

    return WorkflowResult(
        ticket_id=ticket_id,
        reply=text,
        total_tokens=total_tokens,
        cost_usd=cost,
        latency_s=latency,
        passed=passed,
        order_missing=order_missing,
        trace_id=trace_id,
        trace_url=trace_url,
    )


def _finalize_trace(lf, lf_trace, output: dict, metadata: dict) -> tuple[str | None, str | None]:
    """Update trace, flush, and return (trace_id, trace_url)."""
    if not lf_trace:
        return None, None
    try:
        lf_trace.update(output=output, metadata=metadata)
        lf.flush()
        tid = str(lf_trace.id)
        return tid, f"{_LANGFUSE_HOST}/trace/{tid}"
    except Exception:
        return None, None


if __name__ == "__main__":
    from agent.tickets import EXPECTED

    ticket_id = sys.argv[1] if len(sys.argv) > 1 else "T001"
    print(f"\n=== Workflow run: {ticket_id} ===")
    result = run_workflow(ticket_id, expected_verdict=EXPECTED.get(ticket_id), verbose=True)
    print(f"\nReply:\n{result.reply[:400]}")
    print(
        f"\nTokens: {result.total_tokens} | Cost: ${result.cost_usd:.6f} | "
        f"Latency: {result.latency_s:.2f}s | Pass: {result.passed}"
    )
    if result.trace_url:
        print(f"Trace: {result.trace_url}")

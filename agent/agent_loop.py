"""Agentic loop for refund-chase ticket resolution.

Enforces four budgets on every lap:
  MAX_ITERS      -- maximum LLM laps (one lap = one LLM call)
  MAX_TOKENS     -- cumulative input+output tokens across all laps
  MAX_COST_USD   -- derived from tokens * per-token price
  MAX_WALL_SECS  -- wall-clock time from loop start

Langfuse traces every run: one trace per ticket, one span per lap,
one generation per LLM call, one span per tool call.

Run a single ticket (verbose mode):
    python -m agent.agent_loop T001

Run with tight budget to demo budget termination:
    python -m agent.agent_loop T008 --tight
"""

import json
import os
import sys
import time
from dataclasses import dataclass

import requests
from dotenv import load_dotenv

from agent.mcp_client import MCPManager
from agent.tickets import score_reply

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

_mcp: MCPManager | None = None


def _get_mcp() -> MCPManager:
    """Lazily connect the MCP manager on first use; retry if previous connect discovered no tools."""
    global _mcp
    if _mcp is None or not _mcp.get_tool_schemas():
        _mcp = MCPManager("mcp_config.json", log_wire=True)
        _mcp.connect()
    return _mcp

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

# Langfuse host for building trace URLs
_LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")).rstrip("/")

COST_PER_1M_TOKENS = 0.90  # USD per 1M tokens

MAX_ITERS = 8
MAX_TOKENS = 8000
MAX_COST_USD = 0.05
MAX_WALL_SECS = 25

DEMO_MAX_ITERS = 2   # tight budget used for the budget-demo run

SYSTEM_PROMPT = (
    "You are a billing support agent resolving refund requests. "
    "You have EXACTLY FOUR tools available -- no others exist:\n"
    "  get_ticket, get_order, get_customer_tier, search_knowledge_base\n"
    "NEVER call any tool not listed above. If you generate a call to any other tool "
    "it will be rejected as an error.\n\n"
    "For each ticket, call the tools in this order:\n"
    "1. get_ticket -- retrieve the ticket text, customer ID, and order ID.\n"
    "2. get_order -- fetch purchase date, amount, and fulfilment status. "
    "If the order is not found, note it as missing.\n"
    "3. get_customer_tier -- retrieve the customer's refund window in days.\n"
    "4. Draft a concise reply: approve the refund if days_since_purchase is within "
    "refund_days, deny it if outside, or escalate (tell the customer to email "
    "billing@company.com) if the order could not be found.\n"
    "You also have search_knowledge_base, but it is NOT needed for ordinary refund "
    "requests (duplicate charge, wrong amount, order not found, etc.) -- those are "
    "resolved from get_ticket/get_order/get_customer_tier alone. Only call "
    "search_knowledge_base if the ticket text contains an explicit error code "
    "(format like ERR-nnnn or PAY-nnnn) or explicitly asks about a named policy, "
    "migration procedure, or account-role rule you cannot answer from the ticket/order "
    "data. When in doubt, do not call it.\n"
    "Do not guess -- always call all three tools before drafting the reply."
)

FREEFORM_SYSTEM_PROMPT = (
    "You are a helpful billing support agent for an e-commerce company. "
    "You have EXACTLY FOUR tools available -- no others exist:\n"
    "  search_knowledge_base, get_ticket, get_order, get_customer_tier\n"
    "NEVER call any tool not listed above. If you generate a call to any other tool "
    "it will be rejected as an error.\n\n"
    "Tool descriptions:\n"
    "- search_knowledge_base(query): search the billing knowledge base for policies, error codes, "
    "migration procedures, and documented answers\n"
    "- get_ticket(ticket_id): look up a support ticket by ID (e.g. T001)\n"
    "- get_order(order_id): look up an order by ID (e.g. O201)\n"
    "- get_customer_tier(customer_id): look up a customer's service tier and refund window\n\n"
    "RULES -- follow these strictly, do not skip:\n"
    "1. Only call search_knowledge_base if the question contains an explicit error code "
    "(format like ERR-nnnn or PAY-nnnn) or explicitly names a documented policy, migration "
    "procedure, or account-role rule you cannot answer from ticket/order data. Do NOT call it "
    "for ordinary refund, order-status, or ticket-history questions. Call it at most once per "
    "question -- never repeat it with a reworded query.\n"
    "2. If the question mentions a ticket ID (T001...) -- call get_ticket, then get_order, then "
    "get_customer_tier, unless the question is only asking about ticket history or escalation.\n"
    "3. Only answer directly (without tools) for purely conversational messages like greetings.\n"
    "4. Never call the same tool with the same arguments more than once.\n"
    "After retrieving results, give a concise, grounded answer based only on what the tools returned."
)


@dataclass
class AgentResult:
    ticket_id: str
    reply: str
    laps: int
    total_tokens: int
    cost_usd: float
    latency_s: float
    passed: bool
    budget_hit: str | None = None
    error: str | None = None
    trace_id: str | None = None
    trace_url: str | None = None


class BudgetExceeded(Exception):
    def __init__(self, budget: str, value, limit):
        self.budget = budget
        self.value = value
        self.limit = limit
        super().__init__(f"BUDGET_HIT budget={budget} value={value} limit={limit}")


def _groq_call(messages: list[dict], tools: list[dict]) -> dict:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set in .env")
    if not tools:
        raise RuntimeError(
            "No MCP tools available -- MCP server is not connected. "
            "Restart the backend server to reconnect."
        )

    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.0,
    }

    wait = 10
    for attempt in range(4):
        try:
            resp = requests.post(
                f"{GROQ_BASE_URL}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=60,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Groq request failed: {exc}") from exc

        if resp.status_code == 429:
            if attempt == 3:
                raise RuntimeError("Groq 429 rate-limit after 4 retries")
            retry_after = int(resp.headers.get("Retry-After", wait))
            print(f"  [rate-limit] 429 -- retrying in {retry_after}s", flush=True)
            time.sleep(retry_after)
            wait = min(wait * 2, 60)
            continue

        if resp.status_code == 400:
            try:
                err_body = resp.json().get("error", {})
                if err_body.get("code") == "tool_use_failed":
                    import re as _re
                    failed_gen = err_body.get("failed_generation", "{}")
                    m = _re.search(r'"name"\s*:\s*"([^"]+)"', failed_gen)
                    unknown_name = m.group(1) if m else "unknown_tool"
                    # Return a synthetic response so the agent loop can feed back
                    # "unknown tool" to the model and let it retry with a real tool.
                    return {
                        "choices": [{
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [{
                                    "id": "call_hallucinated_0",
                                    "type": "function",
                                    "function": {
                                        "name": unknown_name,
                                        "arguments": "{}",
                                    },
                                }],
                            },
                        }],
                        "usage": {"total_tokens": 50, "prompt_tokens": 50, "completion_tokens": 0},
                    }
            except Exception:
                pass

        try:
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Groq API error {resp.status_code}: {resp.text[:200]}") from exc

        return resp.json()

    raise RuntimeError("Groq call failed after all retries")


def run_agent(
    ticket_id: str = "",
    expected_verdict: str | None = None,
    max_iters: int = MAX_ITERS,
    max_tokens: int = MAX_TOKENS,
    max_cost: float = MAX_COST_USD,
    max_wall: float = MAX_WALL_SECS,
    verbose: bool = False,
    on_step=None,  # callable(dict) -- receives live step events for streaming UIs
    user_message: str | None = None,       # free-form text; overrides ticket_id user turn
    system_prompt_override: str | None = None,  # replaces SYSTEM_PROMPT when set
    dispatch_override=None,  # callable(name, args_json) -- replaces dispatch_tool when set
) -> AgentResult:
    t_start = time.monotonic()
    cumulative_tokens = 0
    laps = 0

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
                name="agent_run",
                input={"ticket_id": ticket_id, "ticket_text": ticket_text},
                tags=["agent", "week7-task-a"],
                metadata={
                    "system": "agent",
                    "model": MODEL,
                    "max_iters": max_iters,
                    "max_tokens": max_tokens,
                    "max_cost_usd": max_cost,
                    "max_wall_secs": max_wall,
                    "expected_verdict": expected_verdict,
                },
            )
        except Exception:
            lf_trace = None

    active_system = system_prompt_override or SYSTEM_PROMPT
    active_user = user_message if user_message else f"Resolve ticket {ticket_id}."
    messages: list[dict] = [
        {"role": "system", "content": active_system},
        {"role": "user", "content": active_user},
    ]
    _seen_calls: set[tuple[str, str]] = set()

    def _check_budgets():
        elapsed = time.monotonic() - t_start
        cost = (cumulative_tokens / 1_000_000) * COST_PER_1M_TOKENS
        if laps >= max_iters:
            raise BudgetExceeded("max_iters", laps, max_iters)
        if cumulative_tokens >= max_tokens:
            raise BudgetExceeded("max_tokens", cumulative_tokens, max_tokens)
        if cost >= max_cost:
            raise BudgetExceeded("max_cost_usd", round(cost, 6), max_cost)
        if elapsed >= max_wall:
            raise BudgetExceeded("max_wall_secs", round(elapsed, 1), max_wall)

    lf_lap_span = None

    def _emit(step: dict):
        if on_step:
            try:
                on_step(step)
            except Exception:
                pass

    try:
        while True:
            _check_budgets()

            _emit({"type": "thinking", "lap": laps + 1})

            # Start lap span
            if lf_trace:
                try:
                    lf_lap_span = lf_trace.span(
                        name=f"lap_{laps + 1}",
                        input={
                            "messages_count": len(messages),
                            "cumulative_tokens": cumulative_tokens,
                        },
                    )
                except Exception:
                    lf_lap_span = None

            data = _groq_call(messages, _get_mcp().get_tool_schemas())
            choice = data["choices"][0]
            usage = data.get("usage", {})
            lap_tokens = usage.get("total_tokens", 0)
            cumulative_tokens += lap_tokens
            laps += 1

            finish_reason = choice.get("finish_reason", "")
            msg = choice["message"]
            tool_calls = msg.get("tool_calls") or []

            _emit({"type": "llm_response", "lap": laps, "finish_reason": finish_reason, "lap_tokens": lap_tokens, "cumulative_tokens": cumulative_tokens})

            if verbose:
                print(
                    f"  [lap {laps}] finish_reason={finish_reason} "
                    f"lap_tokens={lap_tokens} cumulative={cumulative_tokens}",
                    flush=True,
                )

            # Record the LLM call as a generation inside the lap span
            if lf_lap_span:
                try:
                    lf_gen = lf_lap_span.generation(
                        name="llm_call",
                        model=MODEL,
                        input=messages,
                        metadata={"temperature": 0.0, "lap": laps, "finish_reason": finish_reason},
                    )
                    gen_output = msg.get("content") or f"[{len(tool_calls)} tool_calls]"
                    lf_gen.end(
                        output=gen_output,
                        usage={
                            "input": usage.get("prompt_tokens", 0),
                            "output": usage.get("completion_tokens", 0),
                            "unit": "TOKENS",
                        },
                    )
                except Exception:
                    pass

            if finish_reason == "stop" or not tool_calls:
                reply = (msg.get("content") or "").strip()
                if not reply:
                    # Model returned stop with empty/null content -- treat as error
                    # so the job is marked failed rather than silently showing a blank bubble.
                    raise RuntimeError(
                        "The model returned an empty response. "
                        "Try rephrasing your question or including a ticket ID."
                    )
                cost = (cumulative_tokens / 1_000_000) * COST_PER_1M_TOKENS
                latency = time.monotonic() - t_start
                passed = score_reply(reply, expected_verdict)
                _emit({"type": "done", "reply": reply, "laps": laps, "total_tokens": cumulative_tokens, "cost_usd": round(cost, 6), "latency_s": round(latency, 3), "passed": passed})

                if lf_lap_span:
                    try:
                        lf_lap_span.end(output={"finish_reason": "stop", "reply_chars": len(reply)})
                    except Exception:
                        pass

                trace_id = None
                trace_url = None
                if lf_trace:
                    try:
                        lf_trace.update(
                            output={"reply": reply, "passed": passed, "verdict": expected_verdict},
                            metadata={
                                "laps": laps,
                                "total_tokens": cumulative_tokens,
                                "cost_usd": round(cost, 6),
                                "latency_s": round(latency, 3),
                            },
                        )
                        lf.flush()
                        trace_id = str(lf_trace.id)
                        trace_url = f"{_LANGFUSE_HOST}/trace/{trace_id}"
                    except Exception:
                        pass

                return AgentResult(
                    ticket_id=ticket_id,
                    reply=reply,
                    laps=laps,
                    total_tokens=cumulative_tokens,
                    cost_usd=cost,
                    latency_s=latency,
                    passed=passed,
                    trace_id=trace_id,
                    trace_url=trace_url,
                )

            # Append the assistant message that contains the tool_calls
            messages.append({
                "role": "assistant",
                "content": msg.get("content"),
                "tool_calls": tool_calls,
            })

            # Execute each tool and record as spans inside the lap span
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                fn_args = tc["function"]["arguments"]
                try:
                    args_dict_emit = json.loads(fn_args)
                except Exception:
                    args_dict_emit = {"raw": fn_args}
                mcp_server = _get_mcp().get_server_for_tool(fn_name)
                _emit({"type": "tool_call", "lap": laps, "tool": fn_name, "args": args_dict_emit, "mcp_server": mcp_server})

                call_key = (fn_name, fn_args)
                if call_key in _seen_calls:
                    # Same tool + same arguments already ran this turn -- refuse to
                    # re-dispatch (prevents an unproductive retry loop from burning
                    # the iteration/token budget) and tell the model to move on.
                    result_str = json.dumps({
                        "error": "duplicate_call",
                        "hint": f"{fn_name} was already called with these exact arguments. "
                                "Use the earlier result -- do not repeat this call.",
                    })
                else:
                    _seen_calls.add(call_key)
                    _dispatch = dispatch_override if dispatch_override else _get_mcp().dispatch_tool
                    result_str = _dispatch(fn_name, fn_args)
                try:
                    result_dict_emit = json.loads(result_str)
                except Exception:
                    result_dict_emit = {"raw": result_str}
                _emit({"type": "tool_result", "lap": laps, "tool": fn_name, "result": result_dict_emit, "mcp_server": mcp_server})

                if verbose:
                    args_short = fn_args[:60].replace("\n", " ")
                    res_short = result_str[:80].replace("\n", " ")
                    print(f"    tool: {fn_name}({args_short}) -> {res_short}", flush=True)

                if lf_lap_span:
                    try:
                        args_dict = json.loads(fn_args)
                        result_dict = json.loads(result_str)
                        ts = lf_lap_span.span(name=f"tool_{fn_name}", input=args_dict)
                        ts.end(output=result_dict)
                    except Exception:
                        pass

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_str,
                })

            if lf_lap_span:
                try:
                    lf_lap_span.end(
                        output={"finish_reason": finish_reason, "tool_calls_count": len(tool_calls)}
                    )
                except Exception:
                    pass
            lf_lap_span = None

    except BudgetExceeded as exc:
        cost = (cumulative_tokens / 1_000_000) * COST_PER_1M_TOKENS
        latency = time.monotonic() - t_start
        log_line = (
            f"BUDGET_HIT budget={exc.budget} value={exc.value} "
            f"limit={exc.limit} ticket={ticket_id}"
        )
        print(log_line, flush=True)
        _emit({"type": "budget_hit", "budget": exc.budget, "value": exc.value, "limit": exc.limit, "log": log_line})

        if lf_lap_span:
            try:
                lf_lap_span.end(output={"budget_hit": exc.budget, "value": exc.value})
            except Exception:
                pass

        trace_id = None
        trace_url = None
        if lf_trace:
            try:
                lf_trace.update(
                    output={"passed": False, "budget_hit": log_line},
                    metadata={
                        "laps": laps,
                        "total_tokens": cumulative_tokens,
                        "cost_usd": round(cost, 6),
                        "latency_s": round(latency, 3),
                        "budget_fired": exc.budget,
                    },
                )
                lf.flush()
                trace_id = str(lf_trace.id)
                trace_url = f"{_LANGFUSE_HOST}/trace/{trace_id}"
            except Exception:
                pass

        return AgentResult(
            ticket_id=ticket_id,
            reply="[budget exceeded -- no reply drafted]",
            laps=laps,
            total_tokens=cumulative_tokens,
            cost_usd=cost,
            latency_s=latency,
            passed=False,
            budget_hit=log_line,
            trace_id=trace_id,
            trace_url=trace_url,
        )

    except Exception as exc:
        cost = (cumulative_tokens / 1_000_000) * COST_PER_1M_TOKENS
        latency = time.monotonic() - t_start

        if lf_lap_span:
            try:
                lf_lap_span.end(output={"error": str(exc)})
            except Exception:
                pass

        trace_id = None
        trace_url = None
        if lf_trace:
            try:
                lf_trace.update(
                    output={"error": str(exc), "passed": False},
                    metadata={"laps": laps, "total_tokens": cumulative_tokens},
                )
                lf.flush()
                trace_id = str(lf_trace.id)
                trace_url = f"{_LANGFUSE_HOST}/trace/{trace_id}"
            except Exception:
                pass

        return AgentResult(
            ticket_id=ticket_id,
            reply="[error]",
            laps=laps,
            total_tokens=cumulative_tokens,
            cost_usd=cost,
            latency_s=latency,
            passed=False,
            error=str(exc),
            trace_id=trace_id,
            trace_url=trace_url,
        )


if __name__ == "__main__":
    from agent.tickets import EXPECTED

    ticket_id = sys.argv[1] if len(sys.argv) > 1 else "T001"
    tight = "--tight" in sys.argv

    print(f"\n=== Agent run: {ticket_id} {'(tight budget: MAX_ITERS=2)' if tight else ''} ===")
    result = run_agent(
        ticket_id,
        expected_verdict=EXPECTED.get(ticket_id),
        max_iters=DEMO_MAX_ITERS if tight else MAX_ITERS,
        verbose=True,
    )
    print(f"\nReply:\n{result.reply[:400]}")
    print(
        f"\nLaps: {result.laps} | Tokens: {result.total_tokens} | "
        f"Cost: ${result.cost_usd:.6f} | Latency: {result.latency_s:.2f}s | "
        f"Pass: {result.passed}"
    )
    if result.trace_url:
        print(f"Trace: {result.trace_url}")
    if result.budget_hit:
        print(f"\n{result.budget_hit}")
    if result.error:
        print(f"\nError: {result.error}")

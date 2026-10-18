"""Agentic loop for refund-chase ticket resolution.

Enforces four budgets on every lap:
  MAX_ITERS      -- maximum LLM laps (one lap = one LLM call)
  MAX_TOKENS     -- cumulative input+output tokens across all laps
  MAX_COST_USD   -- input and output tokens priced from the catalog's model prices
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
from src.generation.cost import calculate_cost
from src.observability import tracing
from agent.tickets import score_reply

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

_mcps: dict[str, MCPManager] = {}


_mcp_failed_at: dict[str, float] = {}
MCP_RETRY_COOLDOWN_S = 60.0


def _get_mcp(config_path: str = "mcp_config.json", tool_timeout: float = 30.0,
             connect_timeout: float = 30.0) -> MCPManager:
    """One MCP manager per config file, connected on first use.

    A manager whose event loop died, or that discovered no tools, is abandoned and replaced. After a failed
    connection the next attempts fail immediately for a minute instead of each waiting out the full connect
    timeout: when the servers are down, a ticket should escalate in milliseconds, not after three minutes.
    """
    mgr = _mcps.get(config_path)
    if mgr is not None and (not mgr.is_alive() or not mgr.get_tool_schemas()):
        mgr.close()
        _mcps.pop(config_path, None)
        mgr = None
    if mgr is None:
        since = time.monotonic() - _mcp_failed_at.get(config_path, -1e9)
        if since < MCP_RETRY_COOLDOWN_S:
            raise RuntimeError(f"MCP servers unavailable: the last connection attempt failed {since:.0f}s ago")
        mgr = MCPManager(config_path, log_wire=True, tool_timeout=tool_timeout, connect_timeout=connect_timeout)
        try:
            mgr.connect()
        except Exception:
            _mcp_failed_at[config_path] = time.monotonic()
            raise
        _mcps[config_path] = mgr
    return mgr

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
from src.catalog import prompts, settings  # noqa: E402

# Langfuse host for building trace URLs
_LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")).rstrip("/")


# Model, budgets and prompts come from the catalog (Admin, Settings and Admin, Prompts), read at call time.
def model() -> str:
    return settings.get("models.agent")


def budget(name: str):
    """Week 7 loop budgets: max_iters, max_tokens, max_cost_usd, max_wall_s, demo_max_iters."""
    return settings.get(f"week7.{name}")


def system_prompt() -> str:
    return prompts.render("week7.system", support_email=settings.get("week7.support_email"))


def freeform_system_prompt() -> str:
    return prompts.body("week7.freeform")


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
    """One LLM call through the shared gateway (cache, token limiter, retries)."""
    from src.generation import gateway

    if not tools:
        raise RuntimeError(
            "No MCP tools available -- MCP server is not connected. "
            "Restart the backend server to reconnect."
        )
    try:
        return gateway.chat(messages, tools=tools, model=model())
    except gateway.ToolUseFailed as exc:
        import re as _re
        m = _re.search(r'"name"\s*:\s*"([^"]+)"', exc.failed_generation or "")
        unknown_name = m.group(1) if m else "unknown_tool"
        # Synthetic response so the loop can feed "unknown tool" back to the model
        # and let it retry with a real tool.
        return {
            "choices": [{
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_hallucinated_0",
                        "type": "function",
                        "function": {"name": unknown_name, "arguments": "{}"},
                    }],
                },
            }],
            "usage": {"total_tokens": 50, "prompt_tokens": 50, "completion_tokens": 0},
        }
    except gateway.RateLimited as exc:
        raise RuntimeError(f"rate_limited: {exc}") from exc
    except gateway.GatewayError as exc:
        raise RuntimeError(str(exc)) from exc


def run_agent(
    ticket_id: str = "",
    expected_verdict: str | None = None,
    max_iters: int | None = None,      # None = the Week 7 budget from settings
    max_tokens: int | None = None,
    max_cost: float | None = None,
    max_wall: float | None = None,
    verbose: bool = False,
    on_step=None,  # callable(dict) -- receives live step events for streaming UIs
    user_message: str | None = None,       # free-form text; overrides ticket_id user turn
    system_prompt_override: str | None = None,  # replaces SYSTEM_PROMPT when set
    dispatch_override=None,  # callable(name, args_json) -- replaces dispatch_tool when set
    mcp_config: str = "mcp_config.json",   # which MCP servers (and allow-list) this run may use
    request_trace_id: str | None = None,   # id minted at the entry point; injected into MCP tool calls
    tool_timeout: float = 30.0,
    connect_timeout: float = 30.0,         # servers that warm up a model need longer than the default
    tool_call_caps: dict[str, int] | None = None,  # e.g. {"search_help_centre": 2}; enforced in code
    prefetch=None,  # callable(call) run before lap 1; call(name, args) -> result dict, recorded as origin="code"
) -> AgentResult:
    t_start = time.monotonic()
    max_iters = budget("max_iters") if max_iters is None else max_iters
    max_tokens = budget("max_tokens") if max_tokens is None else max_tokens
    max_cost = budget("max_cost_usd") if max_cost is None else max_cost
    max_wall = budget("max_wall_s") if max_wall is None else max_wall
    MODEL = model()
    cumulative_tokens = 0
    cumulative_cost = 0.0
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
            from agent import tickets as fx
            ticket_text = fx.tickets().get(ticket_id, {}).get("text", "")
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

    active_system = system_prompt_override or system_prompt()
    active_user = user_message if user_message else f"Resolve ticket {ticket_id}."
    messages: list[dict] = [
        {"role": "system", "content": active_system},
        {"role": "user", "content": active_user},
    ]
    _seen_calls: set[tuple[str, str]] = set()
    _calls_per_tool: dict[str, int] = {}

    def _check_budgets():
        nonlocal cumulative_cost
        elapsed = time.monotonic() - t_start
        cost = cumulative_cost
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

    def _run_tool(mcp, fn_name: str, fn_args: str, lap: int, origin: str) -> str:
        """Run one tool call (from the model, or prefetched by code) with the duplicate and cap rules."""
        try:
            args_dict_emit = json.loads(fn_args)
        except Exception:
            args_dict_emit = {"raw": fn_args}
        mcp_server = mcp.get_server_for_tool(fn_name)
        _emit({"type": "tool_call", "lap": lap, "tool": fn_name, "args": args_dict_emit,
               "mcp_server": mcp_server, "origin": origin})

        call_key = (fn_name, fn_args)
        with tracing.span(f"tool:{fn_name}", "tool", trace_id=request_trace_id,
                          server=mcp_server, lap=lap, origin=origin) as tool_span:
            if call_key in _seen_calls:
                # Same tool + same arguments already ran this turn -- refuse to
                # re-dispatch (prevents an unproductive retry loop from burning
                # the iteration/token budget) and tell the model to move on.
                result_str = json.dumps({
                    "error": "duplicate_call",
                    "hint": f"{fn_name} was already called with these exact arguments. "
                            "Use the earlier result -- do not repeat this call.",
                })
            elif tool_call_caps and _calls_per_tool.get(fn_name, 0) >= tool_call_caps.get(fn_name, 10**9):
                # A prompt asking for "at most twice" is a request; this is the limit.
                result_str = json.dumps({
                    "error": "call_limit_reached",
                    "tool": fn_name,
                    "limit": tool_call_caps[fn_name],
                    "instruction": "Do not call this tool again. Answer from what you have, or escalate.",
                })
            else:
                _seen_calls.add(call_key)
                _calls_per_tool[fn_name] = _calls_per_tool.get(fn_name, 0) + 1
                if dispatch_override:
                    result_str = dispatch_override(fn_name, fn_args)
                else:
                    result_str = mcp.dispatch_tool(fn_name, fn_args, trace_id=request_trace_id,
                                                   parent_span_id=tool_span.span_id)
            try:
                _tool_ok = "error" not in json.loads(result_str)
            except Exception:
                _tool_ok = True
            tool_span.set(ok=_tool_ok, status="ok" if _tool_ok else "error")
        try:
            result_dict_emit = json.loads(result_str)
        except Exception:
            result_dict_emit = {"raw": result_str}
        _emit({"type": "tool_result", "lap": lap, "tool": fn_name, "result": result_dict_emit,
               "mcp_server": mcp_server, "origin": origin})
        return result_str

    try:
        # Connected inside the try so a connection failure becomes an error result, not a crash.
        mcp = _get_mcp(mcp_config, tool_timeout, connect_timeout)

        if prefetch:
            # Calls code always makes (the model would make them on lap 1 anyway). Their results enter the
            # conversation as completed tool calls, so the model usually answers in one lap instead of three.
            # Every other tool stays available to the model.
            def _prefetch_call(name: str, args: dict) -> dict:
                call_id = f"prefetch_{len(messages)}"
                fn_args = json.dumps(args)
                result_str = _run_tool(mcp, name, fn_args, 0, "code")
                messages.append({"role": "assistant", "content": None, "tool_calls": [
                    {"id": call_id, "type": "function", "function": {"name": name, "arguments": fn_args}}]})
                messages.append({"role": "tool", "tool_call_id": call_id, "content": result_str})
                try:
                    return json.loads(result_str)
                except Exception:
                    return {"raw": result_str}
            prefetch(_prefetch_call)

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

            with tracing.span("llm_call", "llm", trace_id=request_trace_id, model=MODEL, lap=laps + 1) as llm_span:
                data = _groq_call(messages, mcp.get_tool_schemas())
                _usage = data.get("usage") or {}
                _gw = data.get("gateway") or {}
                _in, _out = _usage.get("prompt_tokens", 0), _usage.get("completion_tokens", 0)
                llm_span.set(
                    input_tokens=_in,
                    output_tokens=_out,
                    cost_usd=calculate_cost(MODEL, _in, _out)["total_cost_usd"],
                    cache=_gw.get("cache"),
                    waited_s=_gw.get("waited_s", 0),
                    attempts=_gw.get("attempts"),
                    finish_reason=data["choices"][0].get("finish_reason"),
                )
            choice = data["choices"][0]
            usage = data.get("usage", {})
            lap_tokens = usage.get("total_tokens", 0)
            cumulative_tokens += lap_tokens
            cumulative_cost += calculate_cost(MODEL, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))["total_cost_usd"]
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
                cost = cumulative_cost
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
                result_str = _run_tool(mcp, fn_name, fn_args, laps, "model")

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
        cost = cumulative_cost
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
        cost = cumulative_cost
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
    from agent import tickets as fx
    ticket_id = sys.argv[1] if len(sys.argv) > 1 else "T001"
    tight = "--tight" in sys.argv

    print(f"\n=== Agent run: {ticket_id} {'(tight budget: MAX_ITERS=2)' if tight else ''} ===")
    result = run_agent(
        ticket_id,
        expected_verdict=fx.expected().get(ticket_id),
        max_iters=budget("demo_max_iters") if tight else budget("max_iters"),
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

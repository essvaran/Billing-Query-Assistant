"""The single entry point: handle_ticket(TicketRequest) -> TicketResponse.

The CLI, the API and the eval suite all call this one function, so the evals grade
exactly what users get.

Flow
  1. mint a trace id
  2. pre-guard: hostile or non-Tier-1 tickets escalate with no model call
  3. agent loop over the MCP tools (discovered at runtime, filtered by the allow-list)
  4. post-guard: entitlement, citation and policy-version checks on the draft
  5. ANSWER only if every check passes; anything else ESCALATES with a handoff row
"""
import re
import time
import uuid

from agent import agent_loop
from src.generation.citations import extract_citations, resolve_citations
from src.observability import tracing
from tier1 import db, guards, prompts, tools, tracing_store
from tier1.customer_text import customer_view
from tier1.flags import ablated
from tier1.models import TicketRequest, TicketResponse

MCP_CONFIG = "mcp_config.tier1.json"
# Budgets and timeouts are settings (Admin, Settings, Tier-1 assistant), read per ticket.


def _setting(name: str):
    from src.catalog import settings
    return settings.get(f"tier1.{name}")


def _escalate_locally(req: TicketRequest, trace_id: str, reason: str, summary: str) -> str:
    """Used when the escalation is decided by code (guards, budget, tool failure).

    The agent's own escalate tool is the same function behind MCP; calling it directly
    keeps escalation working even when the MCP servers are down.
    """
    ref = req.ticket_id or req.order_id or "unreferenced"
    return tools.escalate(ref, reason, summary, trace_id=trace_id)["handoff_id"]


_GREETING = re.compile(r"^\s*(hi|hello|hey|hiya|good (morning|afternoon|evening)|thanks|thank you|ok|okay)\b[\s!.,?]*$", re.I)
_GREETING_REPLY = ("how can I help? I can answer questions about refunds and returns, delivery, payments, "
                   "your plan and your account settings.")

_ERROR_CODE = re.compile(r"\b[A-Z]{2,5}-\d{3,5}\b")


def _search_query(subject: str, body: str) -> str:
    """The first search query, built in code: error codes first (each names one article), then the customer's words."""
    text = f"{subject} {body}".strip()
    codes = list(dict.fromkeys(_ERROR_CODE.findall(text)))
    words = " ".join(text.split())
    return (" ".join(codes) + " " + words).strip()[:_setting("query_chars")]


def _prefetcher(req: TicketRequest):
    """Make the two calls every Tier-1 answer needs before the model's first lap.

    The model would make them itself on lap 1 (the prompt requires both); doing it in code saves one or two full
    laps of tokens. They are recorded with origin="code" so the trajectory eval does not credit the model for them.
    """
    if ablated("prefetch"):
        return None

    def run(call) -> None:
        version = ""
        if req.customer_id:
            args = {"customer_id": req.customer_id}
            if req.order_id:
                args["order_id"] = req.order_id
            ent = call("check_entitlement", args)
            if "error" in ent and req.order_id:
                # An order we cannot find must not take the customer's policy with it: the reply can still
                # say what the policy is and ask for the right order number.
                ent = call("check_entitlement", {"customer_id": req.customer_id})
            if "error" not in ent:
                version = ent.get("policy_version") or ""
        call("search_help_centre", {"query": _search_query(req.subject, req.body), "policy_version": version})
    return run


def _events_from_steps(steps: list[dict]) -> list[guards.ToolEvent]:
    events, pending = [], {}
    for step in steps:
        if step.get("type") == "tool_call":
            pending[step["tool"]] = step.get("args") or {}
        elif step.get("type") == "tool_result":
            result = step.get("result")
            events.append(guards.ToolEvent(step["tool"], pending.pop(step["tool"], {}),
                                           result if isinstance(result, dict) else {"raw": result}))
    return events


def _retrieved(events: list[guards.ToolEvent]) -> list[dict]:
    hits: list[dict] = []
    for ev in events:
        if ev.name == "search_help_centre":
            hits.extend(ev.result.get("results", []))
    return hits


def handle_ticket(req: TicketRequest, on_step=None) -> TicketResponse:
    """The single entry point. Opens the root span; every other span hangs under it.

    on_step, when given, receives each progress event (guard results, tool calls and results) so a UI
    can show the work as it happens. It never affects the outcome.
    """
    trace_id = req.trace_id or uuid.uuid4().hex
    db.init_db()
    tracing_store.install()
    with tracing.span("ticket", "request", trace_id=trace_id, ticket_id=req.ticket_id,
                      customer_id=req.customer_id, body_chars=len(req.body)) as root:
        resp = _handle(req, trace_id, on_step)
        root.set(decision=resp.decision, reason=resp.reason or None, laps=resp.laps,
                 tools=resp.tools_called, violations=[v["code"] for v in resp.violations])
    return resp


def _handle(req: TicketRequest, trace_id: str, on_step=None) -> TicketResponse:
    started = time.perf_counter()

    def emit(event: dict) -> None:
        if on_step:
            try:
                on_step(event)
            except Exception:
                pass

    def done(resp: TicketResponse) -> TicketResponse:
        resp.latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return resp

    # 2. pre-guard: no model call, no model cost
    with tracing.span("pre_guard", "guard") as g:
        block = guards.pre_guard(req.subject, req.body)
        g.set(blocked=bool(block), category=block.category if block else None)
    emit({"type": "guard", "stage": "pre", "blocked": bool(block), "category": block.category if block else None})
    if block:
        handoff = _escalate_locally(req, trace_id, block.reason, f"pre-guard: {block.category}")
        return done(TicketResponse("ESCALATE", "", trace_id, reason=block.reason, handoff_id=handoff,
                                   violations=[{"code": block.category, "detail": block.detail}]))

    if _GREETING.match(req.body or "") and not req.subject.strip():
        first_name = ((db.get_customer(req.customer_id) or {}).get("name") or "").split(" ")[0]
        reply = (f"Hi {first_name}, " if first_name else "Hi, ") + _GREETING_REPLY
        return done(TicketResponse("ANSWER", reply, trace_id, customer_reply=reply))

    # 3. agent loop
    steps: list[dict] = []
    for attempt in (1, 2):   # one retry: a provider or MCP hiccup should not cost a customer a human handoff
        steps.clear()
        try:
            with tracing.span("mcp_connect", "setup") as cs:
                # Near zero once the process is warm; about 13 s on the first ticket of a cold process,
                # because the help-centre server loads its embedding model before it serves.
                mcp = agent_loop._get_mcp(MCP_CONFIG, _setting("tool_timeout_s"), _setting("connect_timeout_s"))
                cs.set(tools=len(mcp.get_tool_schemas()), blocked=len(mcp.blocked_tools()))
            result = agent_loop.run_agent(
                ticket_id=req.ticket_id,
                user_message=prompts.user_message(req.subject, req.body, req.customer_id, req.order_id, req.ticket_id),
                system_prompt_override=prompts.system_prompt(mcp.get_tool_schemas(), prefetched=not ablated("prefetch")),
                on_step=lambda step: (steps.append(step), emit(step)),
                mcp_config=MCP_CONFIG,
                request_trace_id=trace_id,
                tool_timeout=_setting("tool_timeout_s"),
                connect_timeout=_setting("connect_timeout_s"),
                max_iters=_setting("max_laps"),
                max_tokens=_setting("max_tokens"),
                max_wall=_setting("max_wall_s"),
                max_cost=1e9,                      # the Tier-1 budget is laps, tokens and time; cost follows from tokens
                tool_call_caps={"search_help_centre": _setting("max_searches")},
                prefetch=_prefetcher(req),
            )
            break
        except Exception as exc:  # MCP down, provider down: the customer still gets a human
            if attempt == 1 and not str(exc).startswith("rate_limited"):
                continue
            reason = "rate_limited" if str(exc).startswith("rate_limited") else "tool_error"
            handoff = _escalate_locally(req, trace_id, reason, f"agent could not run: {type(exc).__name__}")
            return done(TicketResponse("ESCALATE", "", trace_id, reason=reason, handoff_id=handoff,
                                       error=f"{type(exc).__name__}: {str(exc)[:150]}"))

    events = _events_from_steps(steps)
    try:  # cost from the recorded spans (per-model price), not the loop's flat estimate
        measured = tracing_store.summarize(tracing_store.get_spans(trace_id))["cost_usd"]
    except Exception:
        measured = result.cost_usd
    resp = TicketResponse(
        "ESCALATE", "", trace_id,
        tools_called=[e.name for e in events],
        model_tools_called=[s["tool"] for s in steps if s.get("type") == "tool_call" and s.get("origin") != "code"],
        entitlement=guards.last_entitlement(events),
        order_facts=next((e.result for e in reversed(events) if e.name == "lookup_order" and "error" not in e.result), None),
        laps=result.laps, total_tokens=result.total_tokens, cost_usd=round(measured, 6),
    )

    # the agent decided to escalate itself
    for ev in events:
        if ev.name == "escalate" and ev.result.get("status") == "queued":
            resp.reason = ev.args.get("reason", "other")
            resp.handoff_id = ev.result.get("handoff_id", "")
            return done(resp)

    if result.budget_hit or result.error:
        resp.reason = ("rate_limited" if (result.error or "").startswith("rate_limited")
                       else "budget_exceeded" if result.budget_hit else "tool_error")
        resp.budget_hit, resp.error = result.budget_hit or "", result.error or ""
        resp.handoff_id = _escalate_locally(req, trace_id, resp.reason, "agent stopped before answering")
        return done(resp)

    # 4. post-guard on the draft
    reply = result.reply
    retrieved = _retrieved(events)
    cited = extract_citations(reply)
    resolved = resolve_citations(cited, retrieved)
    with tracing.span("post_guard", "guard") as g:
        violations = guards.post_guard(reply, events, resolved, cited, {h["chunk_id"] for h in retrieved})
        g.set(violations=[v.code for v in violations], citations=len(resolved), reply_chars=len(reply))
    emit({"type": "guard", "stage": "post", "violations": [v.code for v in violations], "citations": len(resolved)})
    resp.citations = resolved
    resp.sources = [{k: h.get(k) for k in ("chunk_id", "slug", "policy_version", "doc_type", "last_updated", "text")}
                    for h in retrieved]
    if violations:
        resp.reason = guards.escalation_reason(violations)
        resp.draft = reply
        resp.violations = [v.as_dict() for v in violations]
        resp.handoff_id = _escalate_locally(
            req, trace_id, resp.reason, "draft blocked by guards: " + ", ".join(v.code for v in violations))
        return done(resp)

    # 5. every check passed
    resp.decision, resp.reply = "ANSWER", reply
    first_name = ((db.get_customer(req.customer_id) or {}).get("name") or "").split(" ")[0]
    resp.customer_reply = customer_view(reply, resolved, first_name)
    return done(resp)

"""Per-request tracing: one trace id from ticket in to answer out, one span per step.

Usage
    with tracing.span("ticket", "request", trace_id=tid):          # root: sets the trace
        with tracing.span("llm_call", "llm", model=m) as sp:       # child: parent is automatic
            ...
            sp.set(input_tokens=120, output_tokens=40, cost_usd=0.0001)

A span records start, duration, tokens, cost and status. Free text is never stored: attributes are
passed through redact() before they reach the sink, and callers pass sizes and ids, not content.
Without a sink, spans are cheap no-ops, so code that is not traced behaves exactly as before.

Across a process boundary (the MCP hop) contextvars do not travel. The MCP client passes trace_id
and parent_span_id as hidden tool arguments; the server opens its span with those explicit values.
"""
import contextvars
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable

from src.observability.redact import redact

_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
_span_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("span_id", default=None)
_sink: Callable[[dict], None] | None = None
_warned = False

# Span fields that are columns, not free-form attributes.
_COLUMNS = ("input_tokens", "output_tokens", "cost_usd")


def own_cost(kind: str, cost_usd: float | None) -> float | None:
    """A span's own cost. Only model calls spend money, so any other span costs 0.0 rather than "unknown".
    A model call that recorded no cost (it failed before usage came back) stays None: unknown is the truth there."""
    if cost_usd is not None or kind == "llm":
        return cost_usd
    return 0.0


def set_sink(sink: Callable[[dict], None] | None) -> None:
    global _sink
    _sink = sink


def current_trace_id() -> str | None:
    return _trace_id.get()


def current_span_id() -> str | None:
    return _span_id.get()


def new_id() -> str:
    return uuid.uuid4().hex[:16]


class Span:
    def __init__(self, span_id: str, trace_id: str | None, parent_id: str | None, name: str, kind: str, attrs: dict):
        self.span_id, self.trace_id, self.parent_id = span_id, trace_id, parent_id
        self.name, self.kind = name, kind
        self.attrs = dict(attrs)
        self.status = "ok"
        self.input_tokens: int | None = None
        self.output_tokens: int | None = None
        self.cost_usd: float | None = None

    def set(self, **values: Any) -> None:
        for key, value in values.items():
            if key in _COLUMNS:
                setattr(self, key, value)
            elif key == "status":
                self.status = value
            else:
                self.attrs[key] = value


def _emit(row: dict) -> None:
    global _warned
    if _sink is None:
        return
    try:
        _sink(row)
    except Exception as exc:  # tracing must never break a request
        if not _warned:
            _warned = True
            print(f"[tracing] sink failed: {type(exc).__name__}", file=sys.stderr, flush=True)


@contextmanager
def span(name: str, kind: str, trace_id: str | None = None, parent_id: str | None = None, **attrs: Any):
    tid = trace_id or _trace_id.get()
    sp = Span(new_id(), tid, parent_id or _span_id.get(), name, kind, attrs)
    if tid is None:           # nothing to attach to: still usable, never recorded
        yield sp
        return
    token_t, token_s = _trace_id.set(tid), _span_id.set(sp.span_id)
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    try:
        yield sp
    except BaseException as exc:
        sp.status = "error"
        sp.attrs.setdefault("error", type(exc).__name__)
        raise
    finally:
        _span_id.reset(token_s)
        _trace_id.reset(token_t)
        _emit({
            "trace_id": tid,
            "span_id": sp.span_id,
            "parent_id": sp.parent_id,
            "name": name,
            "kind": kind,
            "started_at": started.isoformat(),
            "duration_ms": round((time.perf_counter() - t0) * 1000, 2),
            "input_tokens": sp.input_tokens,
            "output_tokens": sp.output_tokens,
            "cost_usd": own_cost(kind, sp.cost_usd),
            "status": sp.status,
            "attrs": redact(sp.attrs),
        })

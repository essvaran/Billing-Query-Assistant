"""Traces live only in Langfuse. This module reads and filters them for the Observability page.

Langfuse filters server-side by time window, user (exact), tag and name. Keyword, cost, "unverified"
and error filters are applied here on the traces fetched. API calls are rationed because the Langfuse
plan limits reads (measured on the Hobby plan: 5 list calls and 5 single-trace calls per minute): list
results are cached, one newest-first scan is shared by keyword search, cost statistics and the 10x view,
everything the detail drawer needs comes from data already fetched, and a local budget stops a burst
before Langfuse does.
"""
import logging
import os
import re
import threading
import time
from collections import OrderedDict, deque
from datetime import datetime, timezone

from src.generation import langfuse_client
from src.generation.cost import calculate_cost

logger = logging.getLogger(__name__)

TRACE_NAME = "answer_question"
PAGE_SIZE = 100
REFUSAL_PREFIXES = (
    "I don't have enough information to answer that",
    "I cannot answer that from the indexed help",
)
TRACE_ID_RE = re.compile(r"^[0-9A-Za-z-]{8,64}$")
RECENT_MAX = 500
RECENT_AGE_SECONDS = 3600
PENDING_AGE_SECONDS = 600

_lock = threading.Lock()
_cache = {}
_calls = deque()
_recent = OrderedDict()
_seen = OrderedDict()


class TraceStoreError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


# ------------------------------------------------------------------ settings

def _int_env(name, default):
    try:
        return max(1, int(os.getenv(name, default)))
    except ValueError:
        return int(default)


def cache_seconds():
    return _int_env("LANGFUSE_CACHE_SECONDS", "60")


def max_calls_per_minute():
    return _int_env("LANGFUSE_API_MAX_PER_MIN", "5")


def scan_limit():
    return _int_env("LANGFUSE_SCAN_LIMIT", "200")


def configured():
    return langfuse_client.get_langfuse() is not None


def langfuse_url(trace_id):
    return langfuse_client.trace_url(trace_id)


def valid_trace_id(trace_id):
    return bool(trace_id) and bool(TRACE_ID_RE.match(str(trace_id)))


# ------------------------------------------------------------------ guarded API access

def _client():
    client = langfuse_client.get_langfuse()
    if client is None:
        raise TraceStoreError(
            503, "Langfuse is not configured. Traces are stored only in Langfuse: set LANGFUSE_PUBLIC_KEY and "
                 "LANGFUSE_SECRET_KEY in .env and restart the API."
        )
    return client


def _spend_budget():
    now = time.time()
    with _lock:
        while _calls and now - _calls[0] > 60:
            _calls.popleft()
        if len(_calls) >= max_calls_per_minute():
            wait = int(60 - (now - _calls[0])) + 1
            raise TraceStoreError(429, f"Too many Langfuse reads this minute. Try again in {wait} seconds.")
        _calls.append(now)


def _call(fn, *args, **kwargs):
    _spend_budget()
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        if status == 429:
            body = getattr(exc, "body", None)
            retry = None
            if isinstance(body, dict):
                retry = (body.get("details") or {}).get("retryAfterSeconds")
            raise TraceStoreError(429, "Langfuse rate limit reached. Try again in "
                                       f"{retry if retry else 'a minute'}{' seconds' if retry else ''}.")
        if status == 404:
            raise TraceStoreError(404, "Trace not found in Langfuse")
        logger.warning("Langfuse request failed: %s", exc)
        raise TraceStoreError(502, "Could not read from Langfuse. Check the keys and the network.")


def _cached(key, loader):
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    value = loader()
    with _lock:
        _cache[key] = (now + cache_seconds(), value)
        if len(_cache) > 200:
            for stale in [k for k, v in _cache.items() if v[0] <= now]:
                _cache.pop(stale, None)
    return value


def clear_cache():
    with _lock:
        _cache.clear()
        _calls.clear()
        _recent.clear()
        _seen.clear()


# ------------------------------------------------------------------ normalizing

def _iso(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value) if value else None


def _parse(ts):
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _is_refusal(answer):
    return (answer or "").startswith(REFUSAL_PREFIXES)


def _finish(item):
    """Fill derived fields shared by Langfuse traces and locally remembered records."""
    item["is_refusal"] = _is_refusal(item.get("final_answer"))
    if item.get("unverified") is None:
        item["unverified"] = (item.get("citations_valid") is False) and not item["is_refusal"]
    return item


def normalize(trace):
    """Turn a Langfuse trace (list or detail response) into the shape the page uses."""
    meta = trace.metadata if isinstance(getattr(trace, "metadata", None), dict) else {}
    inp, out = getattr(trace, "input", None), getattr(trace, "output", None)
    question = inp.get("question") if isinstance(inp, dict) else (inp if isinstance(inp, str) else "")
    answer = out.get("final_answer") if isinstance(out, dict) else (out if isinstance(out, str) else "")
    latency = getattr(trace, "latency", None)
    total_ms = meta.get("total_ms")
    if total_ms is None and latency:
        total_ms = round(latency * 1000, 2)
    cost = meta.get("cost_usd")
    if cost is None:
        cost = getattr(trace, "total_cost", None) or 0.0
    tokens_in, tokens_out = meta.get("input_tokens") or 0, meta.get("output_tokens") or 0
    if not cost and (tokens_in or tokens_out):
        # older traces carry token counts but no cost: price them the same way new traces are priced
        cost = calculate_cost(meta.get("model") or "", tokens_in, tokens_out)["total_cost_usd"]
    return _finish({
        "trace_id": trace.id,
        "timestamp": _iso(getattr(trace, "timestamp", None)),
        "question": question or "",
        "final_answer": answer or "",
        "user_email": getattr(trace, "user_id", None),
        "prompt_version": meta.get("prompt_version") or getattr(trace, "version", None) or "unknown",
        "model": meta.get("model") or "",
        "retriever": meta.get("retriever") or "",
        "collection": meta.get("collection") or "",
        "top_k": meta.get("top_k"),
        "temperature": meta.get("temperature"),
        "citations": meta.get("citations") or [],
        "citations_valid": meta.get("citations_valid"),
        "retrieved_chunks": meta.get("retrieved_chunks") or [],
        "retrieval_ms": meta.get("retrieval_ms"),
        "generation_ms": meta.get("generation_ms"),
        "total_ms": total_ms,
        "input_tokens": meta.get("input_tokens") or 0,
        "output_tokens": meta.get("output_tokens") or 0,
        "cost_usd": float(cost or 0.0),
        "unverified": meta.get("unverified"),
        "error": meta.get("error"),
        "reason": out.get("reason") if isinstance(out, dict) else None,
        "tags": list(getattr(trace, "tags", None) or []),
    })


def summary_from_record(record):
    """Same shape, built from the pipeline's own record (used for traces not yet visible in Langfuse)."""
    return _finish({
        "trace_id": record["trace_id"],
        "timestamp": record.get("timestamp"),
        "question": record.get("question") or "",
        "final_answer": record.get("final_answer") or "",
        "user_email": record.get("user_email"),
        "prompt_version": record.get("prompt_version") or "unknown",
        "model": record.get("model") or "",
        "retriever": record.get("retriever") or "",
        "collection": record.get("collection") or "",
        "top_k": record.get("top_k"),
        "temperature": record.get("temperature"),
        "citations": record.get("citations") or [],
        "citations_valid": record.get("citations_valid"),
        "retrieved_chunks": record.get("retrieved_chunks") or [],
        "retrieval_ms": record.get("retrieval_ms"),
        "generation_ms": record.get("generation_ms"),
        "total_ms": record.get("total_ms"),
        "input_tokens": record.get("input_tokens") or 0,
        "output_tokens": record.get("output_tokens") or 0,
        "cost_usd": float(record.get("cost_usd") or 0.0),
        "unverified": None,
        "error": record.get("error"),
        "reason": None,
        "tags": [],
    })


# ------------------------------------------------------------------ remembered traces

def remember(record):
    """Keep a just-answered trace in memory: feedback and the drill can use it before Langfuse shows it."""
    item = summary_from_record(record)
    with _lock:
        _recent[item["trace_id"]] = (time.time(), item)
        while len(_recent) > RECENT_MAX:
            _recent.popitem(last=False)
    return item


def _remember_seen(items):
    with _lock:
        for item in items:
            _seen[item["trace_id"]] = (time.time(), item)
            _seen.move_to_end(item["trace_id"])
        while len(_seen) > 2000:
            _seen.popitem(last=False)


def _lookup_local(trace_id):
    now = time.time()
    with _lock:
        for store, max_age in ((_recent, RECENT_AGE_SECONDS), (_seen, 900)):
            hit = store.get(trace_id)
            if hit and now - hit[0] < max_age:
                return hit[1]
    return None


def _pending_items(exclude_ids):
    now = time.time()
    with _lock:
        return [item for added, item in _recent.values()
                if now - added < PENDING_AGE_SECONDS and item["trace_id"] not in exclude_ids]


# ------------------------------------------------------------------ filtering

def _norm_filters(filters):
    f = dict(filters or {})
    f["keyword"] = (f.get("keyword") or "").strip().lower()
    f["user"] = (f.get("user") or "").strip().lower()
    return f


def matches(item, filters):
    f = _norm_filters(filters)
    when = _parse(item.get("timestamp"))
    if f.get("after") and when and when < _parse(f["after"]):
        return False
    if f.get("before") and when and when > _parse(f["before"]):
        return False
    if f.get("prompt_version") and item.get("prompt_version") != f["prompt_version"]:
        return False
    if f["user"] and f["user"] not in (item.get("user_email") or "").lower():
        return False
    if f["keyword"] and f["keyword"] not in f"{item.get('question', '')} {item.get('final_answer', '')}".lower():
        return False
    if f.get("cost_above") is not None and not item.get("cost_usd", 0.0) > f["cost_above"]:
        return False
    if f.get("unverified") and not item.get("unverified"):
        return False
    if f.get("errors_only") and not item.get("error"):
        return False
    return True


def _needs_local_filtering(filters):
    f = _norm_filters(filters)
    exact_user = "@" in f["user"] and "." in f["user"].split("@")[-1]
    return bool(f["keyword"] or f.get("cost_above") is not None or f.get("unverified")
                or f.get("errors_only") or (f["user"] and not exact_user))


def _server_params(filters):
    f = _norm_filters(filters)
    params = {"name": TRACE_NAME, "order_by": "timestamp.DESC"}
    if f.get("after"):
        params["from_timestamp"] = _parse(f["after"])
    if f.get("before"):
        params["to_timestamp"] = _parse(f["before"])
    if f.get("prompt_version"):
        params["tags"] = [f"prompt:{f['prompt_version']}"]
    if f["user"] and "@" in f["user"] and "." in f["user"].split("@")[-1]:
        params["user_id"] = filters["user"].strip()
    return params


def _key(prefix, params, extra=()):
    return (prefix, tuple(sorted((k, str(v)) for k, v in params.items())), extra)


# ------------------------------------------------------------------ reading

def _fetch_page(client, params, page, limit):
    def load():
        response = _call(client.fetch_traces, page=page, limit=limit, **params)
        return [normalize(t) for t in response.data], getattr(response.meta, "total_items", len(response.data))

    return _cached(_key("page", params, (page, limit)), load)


def _scan(client, params, maximum=None):
    """Newest-first scan of up to `maximum` traces matching the server-side filters."""
    maximum = maximum or scan_limit()

    def load():
        items, total, page = [], 0, 1
        while len(items) < maximum:
            batch, total = _fetch_page_uncached(client, params, page)
            items.extend(batch)
            if len(batch) < PAGE_SIZE or len(items) >= total:
                break
            page += 1
        return items[:maximum], total

    return _cached(_key("scan", params, (maximum,)), load)


def _fetch_page_uncached(client, params, page):
    response = _call(client.fetch_traces, page=page, limit=PAGE_SIZE, **params)
    return [normalize(t) for t in response.data], getattr(response.meta, "total_items", len(response.data))


def search(filters, limit, offset):
    """Filtered, newest-first traces. Returns items plus how much was scanned."""
    client = _client()
    params = _server_params(filters)
    local = _needs_local_filtering(filters)

    if not local and offset % limit == 0:
        items, total = _fetch_page(client, params, offset // limit + 1, limit)
        _remember_seen(items)
        extra = [i for i in _pending_items({i["trace_id"] for i in items}) if matches(i, filters)] if offset == 0 else []
        merged = sorted(extra + items, key=lambda i: i["timestamp"] or "", reverse=True)[:limit] if extra else items
        return {"items": merged, "total": total + len(extra), "scanned": len(items), "truncated": False}

    scanned, available = _scan(client, params)
    _remember_seen(scanned)
    extra = _pending_items({i["trace_id"] for i in scanned})
    pool = sorted(extra + scanned, key=lambda i: i["timestamp"] or "", reverse=True)
    found = [i for i in pool if matches(i, filters)]
    return {
        "items": found[offset:offset + limit],
        "total": len(found),
        "scanned": len(scanned),
        "truncated": available > len(scanned),
    }


def recent_window(days, maximum=None):
    """Traces from the last `days` days, newest first, for cost and traffic statistics.

    Reuses the same unfiltered newest-first scan as keyword search, so it costs no extra Langfuse calls.
    Returns (items, incomplete); incomplete means older traces inside the window were not scanned.
    """
    client = _client()
    cutoff = datetime.fromtimestamp(time.time() - days * 86400, timezone.utc)
    params = {"name": TRACE_NAME, "order_by": "timestamp.DESC"}
    scanned, available = _scan(client, params, maximum)
    _remember_seen(scanned)
    pool = _pending_items({i["trace_id"] for i in scanned}) + scanned
    within = [i for i in pool if (_parse(i["timestamp"]) or cutoff) >= cutoff]
    oldest = min((_parse(i["timestamp"]) for i in scanned if _parse(i["timestamp"])), default=None)
    incomplete = available > len(scanned) and (oldest is None or oldest >= cutoff)
    return within, incomplete


def get_trace(trace_id):
    """One trace as the page shape, or None when Langfuse has no such trace."""
    local = _lookup_local(trace_id)
    if local:
        return local
    client = _client()
    try:
        response = _call(client.fetch_trace, trace_id)
    except TraceStoreError as exc:
        if exc.status == 404:
            return None
        raise
    item = normalize(response.data)
    _remember_seen([item])
    return item

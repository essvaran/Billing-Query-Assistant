"""The one door to the LLM provider (Groq, OpenAI-compatible chat completions).

Why it exists: the agent had its own client that slept 10 to 60 s on a 429, a
second client served generation and the judge, and nothing was cached, so every
eval rerun spent free-tier quota and gave slightly different answers.

What it adds
  * disk cache keyed by the full request (model, messages, tools, temperature)
  * a sliding-window tokens-per-minute limiter, so requests wait BEFORE they are
    refused instead of failing after
  * retries with backoff for 429 and 5xx, honouring Retry-After
  * one exception hierarchy the callers can rely on

Cache modes (env LLM_CACHE)
  readwrite  default: hit the cache, store misses
  off        never read or write the cache
  replay     cache only; a miss raises CacheMiss. Used by CI, which has no API key.
"""
import hashlib
import json
import os
import random
import threading
import time
from collections import deque
from pathlib import Path

import requests
from dotenv import load_dotenv

from src.config import PROJECT_ROOT

load_dotenv()

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
CACHE_DIR = Path(os.getenv("LLM_CACHE_DIR", PROJECT_ROOT / ".cache" / "llm"))


def _setting(key: str):
    from src.catalog import settings
    return settings.get(key)


# Limits are settings (Admin, Settings, Provider limits); LLM_TPM in the environment overrides provider.tpm.
def tpm_limit() -> int:
    return int(_setting("provider.tpm"))


def max_attempts() -> int:
    return int(_setting("provider.max_attempts"))


def max_backoff_s() -> float:
    return float(_setting("provider.max_backoff_s"))

# Indirection so tests can run without real waiting.
_sleep = time.sleep
_now = time.monotonic


class GatewayError(RuntimeError):
    """The LLM call failed after retries."""


class CacheMiss(GatewayError):
    """replay mode and the request is not in the cache."""


class RateLimited(GatewayError):
    """The provider refused for longer than is worth waiting, typically the daily token cap.

    Retrying is pointless (the wait is minutes to hours), and a caller must be able to tell this from a bug.
    """

    def __init__(self, retry_after_s: float, detail: str):
        super().__init__(f"rate limited for {retry_after_s:.0f}s: {detail}")
        self.retry_after_s = retry_after_s
        self.detail = detail


class CircuitOpen(GatewayError):
    """Several calls in a row failed after all their retries, so calls fail fast for a short while instead of
    each one tying up a request thread through a full round of retries against a provider that is down."""


class ToolUseFailed(GatewayError):
    """The provider rejected the model's tool call (it named a tool that does not exist)."""

    def __init__(self, failed_generation: str):
        super().__init__("tool_use_failed")
        self.failed_generation = failed_generation


_lock = threading.Lock()
_window: deque[list] = deque()  # [monotonic time, tokens] in the last 60 s; lists so a request can settle its own entry
CIRCUIT_FAILURES = 5     # consecutive calls that failed after every retry
CIRCUIT_OPEN_S = 60.0    # how long calls then fail fast
_circuit = {"failures": 0, "open_until": 0.0}
stats = {"hits": 0, "misses": 0, "calls": 0, "waited_s": 0.0, "retries": 0}


def cache_mode() -> str:
    mode = os.getenv("LLM_CACHE", "readwrite").lower()
    return mode if mode in ("readwrite", "off", "replay") else "readwrite"


def cache_key(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def _cache_path(key: str) -> Path:
    return CACHE_DIR / key[:2] / f"{key}.json"


def _cache_get(key: str) -> dict | None:
    path = _cache_path(key)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _cache_put(key: str, data: dict) -> None:
    path = _cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)  # atomic: a reader never sees half a file


def estimate_tokens(payload: dict) -> int:
    """Rough input estimate (4 characters per token) plus room for the answer."""
    return len(json.dumps(payload.get("messages", []))) // 4 + len(json.dumps(payload.get("tools", []))) // 4 + 400


def _acquire_entry(estimated: int) -> tuple[float, list]:
    """Block until the tokens-per-minute window has room. Returns (seconds waited, this request's window entry)."""
    estimated = min(estimated, tpm_limit())  # one oversized request must not wait forever
    waited = 0.0
    while True:
        with _lock:
            now = _now()
            while _window and now - _window[0][0] >= 60:
                _window.popleft()
            used = sum(t for _, t in _window)
            if used + estimated <= tpm_limit() or not _window:
                entry = [now, estimated]
                _window.append(entry)
                return waited, entry
            wait = _window[0][0] + 60 - now + 0.25
        _sleep(wait)
        waited += wait


def _acquire(estimated: int) -> float:
    """Block until the tokens-per-minute window has room. Returns seconds waited."""
    return _acquire_entry(estimated)[0]


def _settle(entry: list, actual: int) -> None:
    """Replace this request's estimate with the real token count (its own entry, not one that merely has the
    same estimate)."""
    with _lock:
        entry[1] = actual


def _circuit_check() -> None:
    with _lock:
        if _now() < _circuit["open_until"]:
            raise CircuitOpen(f"model provider failing; calls paused for {_circuit['open_until'] - _now():.0f}s")


def _circuit_result(ok: bool) -> None:
    with _lock:
        if ok:
            _circuit["failures"] = 0
            return
        _circuit["failures"] += 1
        if _circuit["failures"] >= CIRCUIT_FAILURES:
            _circuit["open_until"] = _now() + CIRCUIT_OPEN_S
            _circuit["failures"] = 0


def _backoff(attempt: int, retry_after: str | None) -> float:
    if retry_after:
        try:
            return min(float(retry_after), max_backoff_s())
        except ValueError:
            pass
    return min(2 ** attempt * 2 + random.random(), max_backoff_s())


def chat(messages: list[dict], tools: list[dict] | None = None, model: str | None = None,
         temperature: float = 0.0, timeout: float = 60.0, cache: bool = True) -> dict:
    """Chat completion. Returns the provider's response dict plus a `gateway` entry
    ({"cache": "hit"|"miss"|"off", "waited_s": float, "attempts": int}).

    cache=False skips the response cache for this call (a replay that must reach the model).
    Raises CacheMiss (replay mode), ToolUseFailed, CircuitOpen, or GatewayError.
    """
    payload: dict = {"model": model or _setting("models.agent"), "messages": messages, "temperature": temperature}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    mode = cache_mode() if cache else "off"
    key = cache_key(payload)
    if mode != "off":
        cached = _cache_get(key)
        if cached is not None:
            stats["hits"] += 1
            return {**cached, "gateway": {"cache": "hit", "waited_s": 0.0, "attempts": 0}}
        if mode == "replay":
            raise CacheMiss(f"no cached response for request {key[:12]} (LLM_CACHE=replay)")

    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise GatewayError("GROQ_API_KEY is not set")

    _circuit_check()
    estimated = estimate_tokens(payload)
    waited, entry = _acquire_entry(estimated)
    stats["calls"] += 1
    last_error = "unknown"
    for attempt in range(1, max_attempts() + 1):
        try:
            resp = requests.post(
                f"{GROQ_BASE_URL}/chat/completions", json=payload, timeout=timeout,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
        except requests.RequestException as exc:
            last_error = type(exc).__name__
            resp = None

        if resp is not None:
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError:
                    data = None
                if not isinstance(data, dict) or not data.get("choices"):
                    last_error = "invalid_response"          # a proxy page or a truncated body: retry it
                    if attempt == max_attempts():
                        break
                    stats["retries"] += 1
                    delay = _backoff(attempt, None)
                    _sleep(delay)
                    waited += delay
                    continue
                _circuit_result(True)
                _settle(entry, int((data.get("usage") or {}).get("total_tokens", estimated)))
                if mode != "off":
                    _cache_put(key, data)
                stats["misses"] += 1
                stats["waited_s"] += waited
                return {**data, "gateway": {"cache": "miss" if mode != "off" else "off",
                                            "waited_s": round(waited, 2), "attempts": attempt}}
            if resp.status_code == 400:
                err = {}
                try:
                    err = resp.json().get("error", {})
                except ValueError:
                    pass
                if err.get("code") == "tool_use_failed":
                    raise ToolUseFailed(err.get("failed_generation", ""))
                raise GatewayError(f"provider rejected the request (400): {str(err.get('message', ''))[:200]}")
            if resp.status_code not in (429, 500, 502, 503, 504):
                raise GatewayError(f"provider error {resp.status_code}")
            last_error = f"http_{resp.status_code}"
            if resp.status_code == 429:
                message = ""
                try:
                    message = str(resp.json().get("error", {}).get("message", ""))
                except ValueError:
                    pass
                try:
                    wait = float(resp.headers.get("Retry-After", "0"))
                except ValueError:
                    wait = 0.0
                if "per day" in message.lower() or wait > max_backoff_s():
                    # keep only the part before the upsell text; it carries the limit, usage and reset time
                    raise RateLimited(wait, message.split(" Need more tokens")[0][:300])

        if attempt == max_attempts():
            break
        stats["retries"] += 1
        delay = _backoff(attempt, resp.headers.get("Retry-After") if resp is not None else None)
        _sleep(delay)
        waited += delay
    _circuit_result(False)
    raise GatewayError(f"LLM call failed after {max_attempts()} attempts ({last_error})")

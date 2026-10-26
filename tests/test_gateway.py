"""LLM gateway: cache, replay mode, retries, limiter (no network, no real waiting)."""
import pytest

from src.generation import gateway

OK = {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "hi"}}],
      "usage": {"total_tokens": 100, "prompt_tokens": 90, "completion_tokens": 10}}


class FakeResp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body if body is not None else OK, headers or {}

    def json(self):
        return self._body


@pytest.fixture()
def gw(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("LLM_CACHE", "readwrite")
    sleeps = []
    monkeypatch.setattr(gateway, "_sleep", sleeps.append)
    monkeypatch.setattr(gateway, "_window", gateway.deque())
    monkeypatch.setattr(gateway, "_circuit", {"failures": 0, "open_until": 0.0})
    for k in gateway.stats:
        gateway.stats[k] = 0
    gateway.sleeps = sleeps
    return gateway


def _post(monkeypatch, responses):
    calls = []

    def fake(url, json=None, headers=None, timeout=None):
        calls.append(json)
        return responses[min(len(calls) - 1, len(responses) - 1)]

    monkeypatch.setattr(gateway.requests, "post", fake)
    return calls


MSG = [{"role": "user", "content": "hello"}]


def test_second_identical_request_is_served_from_cache(gw, monkeypatch):
    calls = _post(monkeypatch, [FakeResp()])
    first = gw.chat(MSG, model="m")
    second = gw.chat(MSG, model="m")
    assert len(calls) == 1
    assert first["gateway"]["cache"] == "miss" and second["gateway"]["cache"] == "hit"
    assert second["usage"]["total_tokens"] == 100  # original usage preserved for cost accounting


def test_different_model_is_a_different_cache_entry(gw, monkeypatch):
    calls = _post(monkeypatch, [FakeResp()])
    gw.chat(MSG, model="a")
    gw.chat(MSG, model="b")
    assert len(calls) == 2


def test_replay_mode_raises_on_miss_and_never_calls_the_network(gw, monkeypatch):
    monkeypatch.setenv("LLM_CACHE", "replay")
    calls = _post(monkeypatch, [FakeResp()])
    with pytest.raises(gw.CacheMiss):
        gw.chat(MSG, model="m")
    assert calls == []


def test_off_mode_never_caches(gw, monkeypatch):
    monkeypatch.setenv("LLM_CACHE", "off")
    calls = _post(monkeypatch, [FakeResp()])
    gw.chat(MSG, model="m")
    gw.chat(MSG, model="m")
    assert len(calls) == 2


def test_429_is_retried_honouring_retry_after(gw, monkeypatch):
    calls = _post(monkeypatch, [FakeResp(429, {}, {"Retry-After": "7"}), FakeResp()])
    out = gw.chat(MSG, model="m")
    assert len(calls) == 2 and out["gateway"]["attempts"] == 2
    assert 7.0 in gw.sleeps


def test_gives_up_after_max_attempts(gw, monkeypatch):
    calls = _post(monkeypatch, [FakeResp(503, {})])
    with pytest.raises(gw.GatewayError):
        gw.chat(MSG, model="m")
    assert len(calls) == gw.max_attempts()


def test_tool_use_failed_is_a_distinct_error_and_is_not_cached(gw, monkeypatch):
    body = {"error": {"code": "tool_use_failed", "failed_generation": '{"name": "made_up"}'}}
    _post(monkeypatch, [FakeResp(400, body)])
    with pytest.raises(gw.ToolUseFailed) as exc:
        gw.chat(MSG, model="m")
    assert "made_up" in exc.value.failed_generation
    monkeypatch.setenv("LLM_CACHE", "replay")
    with pytest.raises(gw.CacheMiss):
        gw.chat(MSG, model="m")


def test_limiter_waits_when_the_minute_window_is_full(gw, monkeypatch):
    from src.catalog import settings
    settings.set("provider.tpm", 1000, "test")
    monkeypatch.delenv("LLM_TPM", raising=False)
    clock = {"t": 1000.0}
    monkeypatch.setattr(gw, "_now", lambda: clock["t"])
    monkeypatch.setattr(gw, "_sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    assert gw._acquire(800) == 0.0          # fits
    waited = gw._acquire(800)               # 1600 > 1000: must wait for the first to age out
    assert waited >= 60.0


def test_limiter_never_waits_forever_for_one_oversized_request(gw, monkeypatch):
    from src.catalog import settings
    settings.set("provider.tpm", 1000, "test")
    monkeypatch.delenv("LLM_TPM", raising=False)
    assert gw._acquire(50_000) == 0.0


def test_daily_token_cap_fails_fast_without_retrying_or_sleeping(gw, monkeypatch):
    body = {"error": {"message": "Rate limit reached ... on tokens per day (TPD): Limit 200000, Used 199313, "
                                 "Requested 2324. Please try again in 11m47s. Need more tokens? Upgrade to Dev Tier."}}
    calls = _post(monkeypatch, [FakeResp(429, body, {"Retry-After": "708"})])
    with pytest.raises(gw.RateLimited) as exc:
        gw.chat(MSG, model="m")
    assert len(calls) == 1 and gw.sleeps == []                       # no retries, no waiting
    assert exc.value.retry_after_s == 708 and "TPD" in exc.value.detail and "Upgrade" not in exc.value.detail


def test_a_short_429_is_still_retried(gw, monkeypatch):
    body = {"error": {"message": "Rate limit reached on tokens per minute (TPM). Please try again in 3s."}}
    calls = _post(monkeypatch, [FakeResp(429, body, {"Retry-After": "3"}), FakeResp()])
    assert gw.chat(MSG, model="m")["gateway"]["attempts"] == 2 and len(calls) == 2


def test_rate_limited_is_a_gateway_error_so_old_callers_still_catch_it(gw):
    assert issubclass(gw.RateLimited, gw.GatewayError)


class NotJson(FakeResp):
    def json(self):
        raise ValueError("not json")


def test_a_200_that_is_not_json_is_retried_not_crashed(gw, monkeypatch):
    calls = _post(monkeypatch, [NotJson(200), FakeResp()])
    out = gw.chat(MSG, model="m")
    assert len(calls) == 2 and out["choices"][0]["message"]["content"] == "hi"


def test_circuit_opens_after_repeated_failures_and_then_fails_fast(gw, monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(gw, "_now", lambda: clock["t"])
    calls = _post(monkeypatch, [FakeResp(503, {})])
    for i in range(gw.CIRCUIT_FAILURES):
        with pytest.raises(gw.GatewayError):
            gw.chat(MSG + [{"role": "user", "content": str(i)}], model="m")
    before = len(calls)
    with pytest.raises(gw.CircuitOpen):
        gw.chat(MSG, model="m")
    assert len(calls) == before                      # no network call while open
    clock["t"] += gw.CIRCUIT_OPEN_S + 1
    _post(monkeypatch, [FakeResp()])
    assert gw.chat(MSG, model="other")["choices"]


def test_cache_false_always_reaches_the_model(gw, monkeypatch):
    calls = _post(monkeypatch, [FakeResp()])
    gw.chat(MSG, model="m", cache=False)
    gw.chat(MSG, model="m", cache=False)
    assert len(calls) == 2


def test_docs_mode_groq_calls_use_the_gateway(gw, monkeypatch):
    from src.generation import llm_client
    calls = _post(monkeypatch, [FakeResp()])
    text, tin, tout = llm_client._ask_groq("sys", "user", "m")
    assert text == "hi" and (tin, tout) == (90, 10) and len(calls) == 1
    _post(monkeypatch, [FakeResp(503, {})])
    with pytest.raises(llm_client.LLMRequestError):
        llm_client._ask_groq("sys", "user2", "m")

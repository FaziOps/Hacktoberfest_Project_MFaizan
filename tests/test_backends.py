import asyncio

import httpx

from app.backends import AutoBackend, GeminiBackend, Reply


class FakeBackend:
    def __init__(self, name, model, error=None):
        self.name, self.model, self.error = name, model, error
        self.calls = 0

    async def generate(self, prompt, image=None, schema=None):
        self.calls += 1
        if self.error:
            raise self.error
        return Reply("{}", f"{self.name}:{self.model}")


def test_auto_uses_gemini_when_it_answers():
    primary, fallback = FakeBackend("gemini", "gemma-4"), FakeBackend("ollama", "gemma4")
    reply = asyncio.run(AutoBackend(primary, fallback).generate("hi"))
    assert reply.model == "gemini:gemma-4"
    assert reply.fallback_reason == ""
    assert fallback.calls == 0


def test_auto_falls_back_offline_when_gemini_fails():
    request = httpx.Request("POST", "https://example.test")
    errors = [
        httpx.ConnectError("no wifi", request=request),
        httpx.HTTPStatusError("rate limited", request=request, response=httpx.Response(429, request=request)),
        RuntimeError("GEMINI_API_KEY is not set"),
        KeyError("candidates"),
    ]
    for error in errors:
        fallback = FakeBackend("ollama", "gemma4")
        reply = asyncio.run(AutoBackend(FakeBackend("gemini", "gemma-4", error), fallback).generate("hi"))
        assert reply.model == "ollama:gemma4"
        assert "answered offline" in reply.fallback_reason
        assert fallback.calls == 1


def test_auto_reports_http_status_in_reason():
    request = httpx.Request("POST", "https://example.test")
    error = httpx.HTTPStatusError("bad key", request=request, response=httpx.Response(400, request=request))
    reply = asyncio.run(AutoBackend(FakeBackend("gemini", "g", error), FakeBackend("ollama", "o")).generate("hi"))
    assert "HTTP 400" in reply.fallback_reason


def _gemini_with(responses, monkeypatch, attempts=4):
    """GeminiBackend whose HTTP calls return `responses` in order; records the models called."""
    calls = []

    def handler(request):
        calls.append(request.url.path.rsplit("/", 1)[-1].split(":")[0])
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def no_sleep(_):
        pass

    monkeypatch.setattr("app.backends.asyncio.sleep", no_sleep)
    backend = GeminiBackend(
        "key", "gemma-4-26b-a4b-it", ("gemma-4-31b-it",), attempts=attempts, transport=httpx.MockTransport(handler)
    )
    return backend, calls


OK_BODY = {"candidates": [{"content": {"parts": [{"text": "hello"}]}}]}


def test_gemini_retries_server_errors_and_switches_model(monkeypatch):
    backend, calls = _gemini_with(
        [httpx.Response(500), httpx.ReadTimeout("slow"), httpx.Response(200, json=OK_BODY)], monkeypatch
    )
    reply = asyncio.run(backend.generate("hi"))
    assert reply.text == "hello"
    assert reply.model == "gemini:gemma-4-26b-a4b-it"
    assert calls == ["gemma-4-26b-a4b-it", "gemma-4-31b-it", "gemma-4-26b-a4b-it"]


def test_gemini_reports_the_model_that_answered(monkeypatch):
    backend, _ = _gemini_with([httpx.Response(429), httpx.Response(200, json=OK_BODY)], monkeypatch)
    assert asyncio.run(backend.generate("hi")).model == "gemini:gemma-4-31b-it"


def test_gemini_does_not_retry_bad_key(monkeypatch):
    backend, calls = _gemini_with([httpx.Response(400), httpx.Response(200, json=OK_BODY)], monkeypatch)
    try:
        asyncio.run(backend.generate("hi"))
    except httpx.HTTPStatusError as exc:
        assert exc.response.status_code == 400
    else:
        raise AssertionError("expected HTTPStatusError")
    assert len(calls) == 1


def test_gemini_gives_up_after_all_attempts(monkeypatch):
    backend, calls = _gemini_with([httpx.Response(500)] * 3, monkeypatch, attempts=3)
    try:
        asyncio.run(backend.generate("hi"))
    except httpx.HTTPStatusError:
        pass
    else:
        raise AssertionError("expected HTTPStatusError")
    assert len(calls) == 3


def test_gemini_without_key_fails_fast():
    try:
        asyncio.run(GeminiBackend("", "gemma-4").generate("hi"))
    except RuntimeError as exc:
        assert "GEMINI_API_KEY" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")

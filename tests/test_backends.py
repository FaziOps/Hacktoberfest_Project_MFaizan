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


def test_gemini_without_key_fails_fast():
    try:
        asyncio.run(GeminiBackend("", "gemma-4").generate("hi"))
    except RuntimeError as exc:
        assert "GEMINI_API_KEY" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")

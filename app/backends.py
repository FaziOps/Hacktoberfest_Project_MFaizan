"""Ways to run Gemma 4: through the Gemini API, locally through Ollama (offline), or both.

The default `auto` backend calls Gemma 4 through the Gemini API and falls back to the
local Gemma 4 in Ollama when the API is unreachable, so the demo never depends on Wi-Fi.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx

from .config import Settings
from .core import fabric_core

Image = tuple[bytes, str]  # (bytes, mime type)


@dataclass
class Reply:
    text: str
    model: str  # "<backend>:<model>", e.g. "gemini:gemma-4-26b-a4b-it"
    fallback_reason: str = ""  # why the primary backend was skipped, if it was


class OllamaBackend:
    name = "ollama"

    def __init__(self, url: str, model: str):
        self.url = url.rstrip("/")
        self.model = model

    async def generate(self, prompt: str, image: Image | None = None, schema: dict | None = None) -> Reply:
        images = [base64.b64encode(image[0]).decode()] if image else []
        payload = fabric_core.build_ollama_payload(self.model, prompt, images, schema)
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(f"{self.url}/api/chat", json=payload)
            response.raise_for_status()
        return Reply(response.json()["message"]["content"], f"{self.name}:{self.model}")

    async def warm_up(self) -> None:
        """Load the model into memory so the first photo is not slow."""
        await self.generate("Reply with OK.")

    async def health(self) -> dict:
        base = {"backend": self.name, "model": self.model}
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.url}/api/tags")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            return {**base, "ok": False, "detail": f"Ollama is not reachable at {self.url}: {exc}"}
        names = {m["name"] for m in response.json().get("models", [])}
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        if wanted not in names:
            return {**base, "ok": False, "detail": f"Model {self.model} is not pulled. Run: ollama pull {self.model}"}
        return {**base, "ok": True, "detail": "Running on this laptop, works offline"}


class GeminiBackend:
    name = "gemini"
    base_url = "https://generativelanguage.googleapis.com/v1beta/models/{model}"

    def __init__(self, api_key: str, model: str, timeout: float = 120):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def generate(self, prompt: str, image: Image | None = None, schema: dict | None = None) -> Reply:
        # Gemma on the Gemini API has no JSON mode, so the schema lives in the prompt
        # and parse_model_json() extracts the object from the reply.
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        parts: list[dict] = [{"text": prompt}]
        if image:
            parts.append({"inline_data": {"mime_type": image[1], "data": base64.b64encode(image[0]).decode()}})
        body = {"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.1}}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.base_url.format(model=self.model) + ":generateContent",
                json=body,
                headers={"x-goog-api-key": self.api_key},
            )
            response.raise_for_status()
        candidate_parts = response.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in candidate_parts if not p.get("thought"))
        return Reply(text, f"{self.name}:{self.model}")

    async def warm_up(self) -> None:
        pass  # nothing to load

    async def health(self) -> dict:
        base = {"backend": self.name, "model": self.model}
        if not self.api_key:
            return {**base, "ok": False, "detail": "GEMINI_API_KEY is not set"}
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(
                    self.base_url.format(model=self.model), headers={"x-goog-api-key": self.api_key}
                )
        except httpx.HTTPError as exc:
            return {**base, "ok": False, "detail": f"Gemini API is not reachable: {exc}"}
        if response.status_code != 200:
            return {**base, "ok": False, "detail": f"Gemini API returned {response.status_code} for {self.model}"}
        return {**base, "ok": True, "detail": "Gemma 4 through the Gemini API"}


# Errors that mean "this backend cannot answer right now", so the fallback should try.
BACKEND_ERRORS = (httpx.HTTPError, RuntimeError, KeyError, IndexError, ValueError)


class AutoBackend:
    """Gemini API first, local Ollama when the API fails (no Wi-Fi, bad key, rate limit)."""

    name = "auto"

    def __init__(self, primary: GeminiBackend, fallback: OllamaBackend):
        self.primary = primary
        self.fallback = fallback
        self.model = primary.model

    async def generate(self, prompt: str, image: Image | None = None, schema: dict | None = None) -> Reply:
        try:
            return await self.primary.generate(prompt, image, schema)
        except BACKEND_ERRORS as exc:
            reason = _describe(exc)
        reply = await self.fallback.generate(prompt, image, schema)
        reply.fallback_reason = f"Gemini API unavailable ({reason}), answered offline"
        return reply

    async def warm_up(self) -> None:
        # Keep the offline model loaded so a fallback is fast.
        await self.fallback.warm_up()

    async def health(self) -> dict:
        primary, fallback = await self.primary.health(), await self.fallback.health()
        if primary["ok"]:
            detail = "Gemini API" + (" · offline fallback ready" if fallback["ok"] else "")
        elif fallback["ok"]:
            detail = f"Offline mode ({primary['detail']})"
        else:
            detail = f"No Gemma 4 available: {primary['detail']}; {fallback['detail']}"
        return {
            "backend": self.name,
            "model": self.model,
            "ok": primary["ok"] or fallback["ok"],
            "detail": detail,
            "backends": [primary, fallback],
        }


def _describe(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.HTTPError):
        return type(exc).__name__
    return str(exc) or type(exc).__name__


def make_backend(settings: Settings) -> OllamaBackend | GeminiBackend | AutoBackend:
    ollama = OllamaBackend(settings.ollama_url, settings.ollama_model)
    if settings.backend == "ollama":
        return ollama
    if settings.backend == "gemini":
        return GeminiBackend(settings.gemini_api_key, settings.gemini_model)
    # Short timeout so a slow network falls back quickly during a live demo.
    return AutoBackend(GeminiBackend(settings.gemini_api_key, settings.gemini_model, timeout=30), ollama)

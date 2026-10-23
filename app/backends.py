"""Two ways to run Gemma 4: locally through Ollama (offline) or through the Gemini API."""

from __future__ import annotations

import base64

import httpx

from .config import Settings
from .core import fabric_core

Image = tuple[bytes, str]  # (bytes, mime type)


class OllamaBackend:
    name = "ollama"

    def __init__(self, url: str, model: str):
        self.url = url.rstrip("/")
        self.model = model

    async def generate(self, prompt: str, image: Image | None = None, schema: dict | None = None) -> str:
        images = [base64.b64encode(image[0]).decode()] if image else []
        payload = fabric_core.build_ollama_payload(self.model, prompt, images, schema)
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(f"{self.url}/api/chat", json=payload)
            response.raise_for_status()
        return response.json()["message"]["content"]

    async def health(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.url}/api/tags")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            return {"ok": False, "detail": f"Ollama is not reachable at {self.url}: {exc}"}
        names = {m["name"] for m in response.json().get("models", [])}
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        if wanted not in names:
            return {"ok": False, "detail": f"Model {self.model} is not pulled. Run: ollama pull {self.model}"}
        return {"ok": True, "detail": "Running locally, works offline"}


class GeminiBackend:
    name = "gemini"
    endpoint = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    async def generate(self, prompt: str, image: Image | None = None, schema: dict | None = None) -> str:
        # Gemma on the Gemini API has no JSON mode, so the schema lives in the prompt
        # and parse_model_json() extracts the object from the reply.
        parts: list[dict] = [{"text": prompt}]
        if image:
            parts.append({"inline_data": {"mime_type": image[1], "data": base64.b64encode(image[0]).decode()}})
        body = {"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.1}}
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                self.endpoint.format(model=self.model),
                json=body,
                headers={"x-goog-api-key": self.api_key},
            )
            response.raise_for_status()
        candidate_parts = response.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in candidate_parts if not p.get("thought"))

    async def health(self) -> dict:
        if not self.api_key:
            return {"ok": False, "detail": "GEMINI_API_KEY is not set"}
        return {"ok": True, "detail": "Gemma 4 through the Gemini API"}


def make_backend(settings: Settings) -> OllamaBackend | GeminiBackend:
    if settings.backend == "gemini":
        return GeminiBackend(settings.gemini_api_key, settings.gemini_model)
    return OllamaBackend(settings.ollama_url, settings.ollama_model)

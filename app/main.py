"""Fabric Inspector web app: photo in, defects and roll grade out."""

from __future__ import annotations

import asyncio
import json
import re
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .backends import BACKEND_ERRORS, AutoBackend, Image, Reply, make_backend
from .config import ROOT, settings
from .core import fabric_core
from .store import Store

ROLL_ID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024

backend = make_backend(settings)
store = Store(settings.data_dir)


async def _warm_up() -> None:
    try:
        await backend.warm_up()
    except BACKEND_ERRORS:
        pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_warm_up())
    yield
    task.cancel()


app = FastAPI(
    title="Fabric Inspector",
    contact={"name": "Muhammad Faizan", "url": "https://github.com/FaziOps"},
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
app.mount("/images", StaticFiles(directory=store.images_dir), name="images")


def _check_roll_id(roll_id: str) -> str:
    if not ROLL_ID.match(roll_id):
        raise HTTPException(400, "Roll number may only use letters, digits, - and _ (max 32)")
    return roll_id


async def ask_json(prompt: str, image: Image | None = None, schema: dict | None = None) -> tuple[dict, Reply]:
    """Ask Gemma 4 for JSON. In auto mode, an unreadable Gemini answer is retried offline."""
    reply = await backend.generate(prompt, image, schema)
    try:
        return fabric_core.parse_model_json(reply.text), reply
    except ValueError:
        if not (isinstance(backend, AutoBackend) and reply.model.startswith("gemini:")):
            raise
    reply = await backend.fallback.generate(prompt, image, schema)
    reply.fallback_reason = "Gemini API reply was not valid JSON, answered offline"
    return fabric_core.parse_model_json(reply.text), reply


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/healthz")
async def healthz() -> dict:
    """Liveness check for the hosting platform. Makes no model calls, so it costs no API quota."""
    return {"ok": True}


@app.get("/api/health")
async def health() -> dict:
    return await backend.health()


@app.post("/api/inspect")
async def inspect(
    image: UploadFile = File(...),
    roll_id: str = Form(...),
    width_cm: float = Form(150),
    length_m: float = Form(10),
    frame_cm: float = Form(30),
) -> dict:
    _check_roll_id(roll_id)
    if width_cm <= 0 or length_m <= 0 or frame_cm <= 0:
        raise HTTPException(400, "Width, length and frame width must be positive")
    mime = (image.content_type or "").split(";")[0]
    if mime not in IMAGE_TYPES:
        raise HTTPException(415, "Upload a JPEG, PNG or WebP photo")
    data = await image.read()
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Photo is empty or larger than 8 MB")

    started = time.perf_counter()
    try:
        raw, reply = await ask_json(fabric_core.build_prompt(frame_cm), (data, mime), fabric_core.RESPONSE_SCHEMA)
        result = fabric_core.normalize(raw)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Gemma 4 call failed: {exc}") from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(502, f"Could not read Gemma 4's answer: {exc}") from exc
    latency_ms = int((time.perf_counter() - started) * 1000)

    store.upsert_roll(roll_id, width_cm, length_m)
    inspection_id = store.add_inspection(roll_id, data, IMAGE_TYPES[mime], result, reply.model, latency_ms)
    return {
        "id": inspection_id,
        "latency_ms": latency_ms,
        "model": reply.model,
        "fallback_reason": reply.fallback_reason,
        **result,
    }


@app.get("/api/rolls/{roll_id}")
async def get_roll(roll_id: str) -> dict:
    roll = store.get_roll(_check_roll_id(roll_id))
    if roll is None:
        raise HTTPException(404, "Roll not found")
    defects = [d for i in roll["inspections"] for d in i["defects"]]
    roll["summary"] = fabric_core.summarize_roll(roll_id, defects, roll["width_cm"], roll["length_m"])
    return roll


@app.delete("/api/rolls/{roll_id}")
async def delete_roll(roll_id: str) -> dict:
    store.delete_roll(_check_roll_id(roll_id))
    return {"deleted": roll_id}


REPORT_PROMPT = """You write shift reports for a textile mill supervisor in Faisalabad.
Below is the inspection summary for one fabric roll and the list of defects found.
Write a short, practical note (3 sentences at most) saying what was found, the grade, and what the
supervisor should do next. Mention the most serious defect. Do not invent numbers.

Reply with JSON only: {{"english": "...", "urdu": "..."}}. The Urdu must be natural Urdu in Urdu script.

Summary: {summary}
Defects: {defects}"""


@app.get("/api/rolls/{roll_id}/report")
async def report(roll_id: str, ai: bool = True) -> dict:
    roll = await get_roll(roll_id)
    summary = roll["summary"]
    result = {**summary, "written_by": "template", "fallback_reason": ""}
    if not ai:
        return result

    defects = [
        {"type": d["type"], "size": d["size"], "points": d["points"], "description": d["description"]}
        for i in roll["inspections"]
        for d in i["defects"]
    ]
    prompt = REPORT_PROMPT.format(
        summary=json.dumps({k: summary[k] for k in ("roll_id", "counts", "total_points", "points_per_100_sq_yd", "grade")}),
        defects=json.dumps(defects, ensure_ascii=False),
    )
    try:
        note, reply = await ask_json(prompt)
        if note.get("english") and note.get("urdu"):
            result.update(
                english=note["english"], urdu=note["urdu"],
                written_by=reply.model, fallback_reason=reply.fallback_reason,
            )
    except BACKEND_ERRORS:
        pass  # the deterministic template is already in `result`
    return result

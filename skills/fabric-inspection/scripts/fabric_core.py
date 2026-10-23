"""Core fabric-inspection logic shared by the Agent Skill and the web app.

Defect catalogue, the Gemma 4 prompt and JSON schema, response parsing, and
grading with the textile industry's 4-point system (ASTM D5430).

Standard library only, so the skill keeps working when this folder is copied
somewhere on its own.
"""

from __future__ import annotations

import json
import re
from collections import Counter

# Defect codes the model may use. `ur` is the Urdu name shown on the mill floor.
DEFECTS: dict[str, dict[str, str]] = {
    "hole": {
        "en": "Hole / cut",
        "ur": "سوراخ",
        "hint": "an opening where yarns are broken right through the fabric",
    },
    "stain": {
        "en": "Stain / oil spot",
        "ur": "داغ",
        "hint": "a discoloured patch: oil, grease, dirt, rust or a dye spot",
    },
    "slub": {
        "en": "Slub (thick yarn)",
        "ur": "موٹا دھاگا",
        "hint": "a short thick place in one yarn that stands out as a lump",
    },
    "broken_yarn": {
        "en": "Broken / missing yarn",
        "ur": "ٹوٹا ہوا دھاگا",
        "hint": "a missing or broken warp end or weft pick, seen as a thin line gap",
    },
    "misweave": {
        "en": "Mis-weave / float",
        "ur": "بُنائی کا نقص",
        "hint": "wrong interlacing, a yarn floating over several others, or a pattern error",
    },
    "shade_variation": {
        "en": "Colour shading",
        "ur": "رنگ کا فرق",
        "hint": "a band or patch that is lighter or darker than the rest of the fabric",
    },
    "crease": {
        "en": "Crease / crush mark",
        "ur": "شکن کا نشان",
        "hint": "a permanent fold line or crushed area",
    },
    "other": {
        "en": "Other defect",
        "ur": "دیگر نقص",
        "hint": "any other clearly visible flaw",
    },
}

# 4-point system: penalty points by the defect's longest dimension.
SIZES: dict[str, dict] = {
    "up_to_3in": {"points": 1, "en": "up to 3 in (7.5 cm)"},
    "3_to_6in": {"points": 2, "en": "3 to 6 in (7.5 to 15 cm)"},
    "6_to_9in": {"points": 3, "en": "6 to 9 in (15 to 23 cm)"},
    "over_9in": {"points": 4, "en": "over 9 in (23 cm)"},
}

# Holes are scored at the maximum, as most export buyers require.
HOLE_POINTS = 4

# Points per 100 square yards. 40 is the usual buyer acceptance limit.
GRADE_LIMITS = (("A", 20.0), ("B", 40.0))
REJECT_GRADE = "C"

IMAGE_QUALITY = ("good", "blurry", "too_dark", "not_fabric")

MIN_CONFIDENCE = 0.35

RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "image_quality": {"type": "string", "enum": list(IMAGE_QUALITY)},
        "fabric": {"type": "string"},
        "defects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": list(DEFECTS)},
                    "size": {"type": "string", "enum": list(SIZES)},
                    "location": {"type": "string"},
                    "confidence": {"type": "number"},
                    "description": {"type": "string"},
                },
                "required": ["type", "size", "location", "confidence", "description"],
            },
        },
    },
    "required": ["image_quality", "fabric", "defects"],
}


def build_prompt(frame_width_cm: float = 30) -> str:
    """Instruction sent to Gemma 4 together with one fabric photo."""
    defect_lines = "\n".join(f"- {code}: {d['hint']}" for code, d in DEFECTS.items())
    size_lines = "\n".join(f"- {code}: {s['en']}" for code, s in SIZES.items())
    return f"""You are an experienced fabric quality inspector in a textile mill in Faisalabad.
Inspect the photo of fabric and list every visible defect.

The photo shows about {frame_width_cm:g} cm of fabric from left to right. Use that to estimate each defect's longest dimension.

Defect type codes (use only these):
{defect_lines}

Size codes (longest dimension of the defect):
{size_lines}

Rules:
- Report each separate defect once.
- The normal weave texture, a printed or woven pattern, and the selvedge edge are NOT defects.
- If the fabric is clean, return an empty "defects" list.
- Set "image_quality" to "blurry", "too_dark" or "not_fabric" when the photo cannot be inspected properly, otherwise "good".
- "location" is where the defect is in the photo, e.g. "top-left", "centre", "bottom edge".
- "confidence" is a number from 0 to 1.
- "fabric" is a short description of the fabric (colour, weave, material if visible).

Reply with JSON only, in this shape:
{{"image_quality": "good", "fabric": "...", "defects": [{{"type": "stain", "size": "up_to_3in", "location": "centre", "confidence": 0.9, "description": "..."}}]}}"""


def build_ollama_payload(model: str, prompt: str, images_b64: list[str], schema: dict | None) -> dict:
    """Body for Ollama's /api/chat. Thinking is off: it adds latency and no accuracy here."""
    message: dict = {"role": "user", "content": prompt}
    if images_b64:
        message["images"] = images_b64
    payload: dict = {
        "model": model,
        "messages": [message],
        "stream": False,
        "think": False,
        "keep_alive": "30m",
        "options": {"temperature": 0.1},
    }
    if schema is not None:
        payload["format"] = schema
    return payload


def parse_model_json(text: str) -> dict:
    """Pull the JSON object out of a model reply, tolerating code fences and chatter."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise ValueError(f"Model reply has no JSON object: {text[:200]!r}")
        return json.loads(cleaned[start : end + 1])


def points_for(defect: dict) -> int:
    if defect["type"] == "hole":
        return HOLE_POINTS
    return SIZES[defect["size"]]["points"]


def normalize(raw: dict, min_confidence: float = MIN_CONFIDENCE) -> dict:
    """Validate a model result, drop low-confidence guesses and add points and names."""
    quality = raw.get("image_quality")
    if quality not in IMAGE_QUALITY:
        quality = "good"

    defects = []
    for item in raw.get("defects") or []:
        if not isinstance(item, dict):
            continue
        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))
        if confidence < min_confidence:
            continue
        code = item.get("type") if item.get("type") in DEFECTS else "other"
        size = item.get("size") if item.get("size") in SIZES else "up_to_3in"
        defect = {
            "type": code,
            "size": size,
            "location": str(item.get("location") or "").strip(),
            "confidence": round(confidence, 2),
            "description": str(item.get("description") or "").strip(),
            "name_en": DEFECTS[code]["en"],
            "name_ur": DEFECTS[code]["ur"],
        }
        defect["points"] = points_for(defect)
        defects.append(defect)

    return {
        "image_quality": quality,
        "fabric": str(raw.get("fabric") or "").strip(),
        "defects": defects,
        "points": sum(d["points"] for d in defects),
    }


def roll_score(total_points: float, width_cm: float, inspected_length_m: float) -> float:
    """Penalty points per 100 square yards of inspected fabric."""
    if width_cm <= 0 or inspected_length_m <= 0:
        raise ValueError("width_cm and inspected_length_m must be positive")
    width_in = width_cm / 2.54
    length_yd = inspected_length_m * 1.0936133
    return round(total_points * 3600 / (width_in * length_yd), 1)


def grade(score: float) -> str:
    for letter, limit in GRADE_LIMITS:
        if score <= limit:
            return letter
    return REJECT_GRADE


ACTIONS = {
    "A": ("Roll passed.", "رول منظور ہے۔"),
    "B": ("Roll passed. Mark the defects for the cutting table.", "رول منظور ہے، مگر نقائص پر نشان لگا دیں۔"),
    "C": ("Roll rejected. Re-inspect and repair before dispatch.", "رول مسترد۔ روانگی سے پہلے دوبارہ معائنہ اور مرمت کریں۔"),
}


def summarize_roll(roll_id: str, defects: list[dict], width_cm: float, inspected_length_m: float) -> dict:
    """Deterministic roll summary in English and Urdu. Never depends on the model."""
    total = sum(d["points"] for d in defects)
    score = roll_score(total, width_cm, inspected_length_m)
    letter = grade(score)
    counts = Counter(d["type"] for d in defects)

    if counts:
        list_en = ", ".join(f"{n} {DEFECTS[c]['en'].lower()}" for c, n in counts.most_common())
        list_ur = "، ".join(f"{n} {DEFECTS[c]['ur']}" for c, n in counts.most_common())
    else:
        list_en, list_ur = "no defects", "کوئی نقص نہیں"

    action_en, action_ur = ACTIONS[letter]
    n = len(defects)
    english = (
        f"Roll {roll_id}: {n} defect{'' if n == 1 else 's'} found ({list_en}). "
        f"{total} penalty points, {score} per 100 sq yd. Grade {letter}. {action_en}"
    )
    urdu = (
        f"رول {roll_id}: {n} {'نقص ملا' if n == 1 else 'نقائص ملے'} ({list_ur})۔ "
        f"کل {total} پوائنٹس، فی 100 مربع گز {score}۔ گریڈ {letter}۔ {action_ur}"
    )
    return {
        "roll_id": roll_id,
        "defect_count": len(defects),
        "counts": dict(counts),
        "total_points": total,
        "points_per_100_sq_yd": score,
        "grade": letter,
        "english": english,
        "urdu": urdu,
    }

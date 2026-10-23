#!/usr/bin/env python3
"""Inspect fabric photos with Gemma 4 running locally in Ollama.

Usage:
    python3 inspect_fabric.py photo1.jpg [photo2.jpg ...] [--model gemma4:latest] [--frame-cm 30]

Prints one JSON object per photo (defects with 4-point penalty points).
Standard library only.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fabric_core  # noqa: E402


def inspect_image(path: Path, model: str, ollama_url: str, frame_cm: float) -> dict:
    image_b64 = base64.b64encode(path.read_bytes()).decode()
    payload = fabric_core.build_ollama_payload(
        model, fabric_core.build_prompt(frame_cm), [image_b64], fabric_core.RESPONSE_SCHEMA
    )
    request = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        reply = json.load(response)["message"]["content"]
    result = fabric_core.normalize(fabric_core.parse_model_json(reply))
    result["image"] = str(path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--model", default=os.environ.get("OLLAMA_MODEL", "gemma4:latest"))
    parser.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    parser.add_argument("--frame-cm", type=float, default=30, help="fabric width visible in the photo, in cm")
    args = parser.parse_args()

    failed = False
    for path in args.images:
        try:
            print(json.dumps(inspect_image(path, args.model, args.ollama_url, args.frame_cm), ensure_ascii=False))
        except (OSError, ValueError, urllib.error.URLError) as exc:
            failed = True
            print(json.dumps({"image": str(path), "error": str(exc)}), file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

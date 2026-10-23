#!/usr/bin/env python3
"""Grade a fabric roll with the 4-point system from inspection results.

Usage:
    python3 inspect_fabric.py *.jpg | python3 grade_roll.py --roll R-14 --width-cm 150 --length-m 10
    python3 grade_roll.py results.jsonl --roll R-14 --width-cm 150 --length-m 10

Input is JSON Lines: one inspect_fabric.py result per line (each with a "defects" list).
Prints the roll summary as JSON, including English and Urdu supervisor notes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fabric_core  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("results", nargs="?", type=Path, help="JSON Lines file (default: stdin)")
    parser.add_argument("--roll", required=True, help="roll number, e.g. R-14")
    parser.add_argument("--width-cm", type=float, required=True, help="fabric width in cm")
    parser.add_argument("--length-m", type=float, required=True, help="length of fabric inspected, in metres")
    args = parser.parse_args()

    lines = args.results.read_text().splitlines() if args.results else sys.stdin.read().splitlines()
    defects = []
    for line in lines:
        if line.strip():
            defects.extend(json.loads(line).get("defects", []))

    summary = fabric_core.summarize_roll(args.roll, defects, args.width_cm, args.length_m)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

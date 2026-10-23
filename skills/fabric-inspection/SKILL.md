---
name: fabric-inspection
description: Inspect photos of woven or knitted fabric for defects (holes, stains, slubs, broken yarns, mis-weaves, colour shading, creases), score them with the textile industry's 4-point system, grade the roll A/B/C, and write a supervisor note in English and Urdu. Use when the user shares fabric or textile photos, asks about fabric quality, roll grading, or a mill inspection report.
license: MIT
metadata:
  author: Muhammad Faizan
compatibility: Needs Python 3.9+. The bundled inspection script calls Gemma 4 through a local Ollama server (default model gemma4:latest).
---

# Fabric inspection

Find defects in fabric photos, score them with the 4-point system (ASTM D5430) and grade the roll.

## When to use

- The user shares one or more photos of fabric and asks what is wrong with it.
- The user wants a roll graded or wants a quality report for a mill supervisor.
- The user asks how the 4-point fabric inspection system works.

## Steps

1. **Collect the roll details.** Ask for anything missing:
   - roll number (for example `R-14`)
   - fabric width in cm
   - length of fabric inspected, in metres
   - roughly how many cm of fabric each photo shows from left to right (default 30)

2. **Inspect each photo.** Prefer the bundled script, which runs Gemma 4 locally:

   ```bash
   python3 scripts/inspect_fabric.py photo1.jpg photo2.jpg --frame-cm 30 > results.jsonl
   ```

   It prints one JSON line per photo. Each defect has `type`, `size`, `location`, `confidence`,
   `description`, the English and Urdu name, and `points`.

   If Ollama is not running and you can see images yourself, inspect the photos directly. Use only the
   defect and size codes in [references/defect-guide.md](references/defect-guide.md), and write one JSON
   line per photo in the same shape:
   `{"defects": [{"type": "stain", "size": "up_to_3in", "points": 1, ...}]}`.

3. **Grade the roll.**

   ```bash
   python3 scripts/grade_roll.py results.jsonl --roll R-14 --width-cm 150 --length-m 10
   ```

   This returns total penalty points, points per 100 square yards, the grade and a ready-made note in
   English and Urdu.

4. **Report back.** Give the user:
   - the grade and points per 100 sq yd
   - each defect with its photo, location and points
   - the supervisor note in Urdu and English
   - any photo flagged `blurry`, `too_dark` or `not_fabric`, with a request to retake it

## Rules

- Never invent defects to fill a report. A clean photo with an empty defect list is a valid result.
- Do not count the normal weave texture, a printed pattern or the selvedge as a defect.
- Treat confidence below 0.35 as noise. The script already drops those.
- Grades: A is 20 points per 100 sq yd or less, B is up to 40 (the usual buyer limit), C is a reject.
- If the photo scale (`--frame-cm`) is unknown, say the size estimates are approximate.

## Files

- `scripts/fabric_core.py`: defect catalogue, Gemma 4 prompt and schema, parsing and 4-point grading. Standard library only.
- `scripts/inspect_fabric.py`: inspects photos with Gemma 4 through Ollama.
- `scripts/grade_roll.py`: grades a roll from inspection results.
- `references/defect-guide.md`: what each defect looks like and how the 4-point system works.

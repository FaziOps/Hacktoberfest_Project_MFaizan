# Fabric Inspector · کپڑا معائنہ

**Point a camera at fabric. Gemma 4 finds the defects, scores them with the textile industry's
4-point system, grades the roll and writes the supervisor's report in Urdu and English.
It runs offline on a laptop.**

Built at Hacktoberfest Hack Day Faisalabad 2026.

## The problem

Faisalabad is Pakistan's textile capital, yet fabric is still inspected by eye. An inspector watches
the fabric run over a lit table, spots defects, adds up penalty points by hand and writes the grade on paper.
It is slow and tiring, and missed defects mean export orders come back rejected.

Off-the-shelf machine-vision systems cost more than most small and mid-sized mills can pay, and they
need an internet connection or specialist setup. Mill floors often have neither.

## What it does

1. **Capture:** press <kbd>Space</kbd> (or upload a photo) while the camera points at the fabric.
2. **Detect:** Gemma 4 looks at the photo and lists every defect: type, size, location and how sure it is.
   It ignores the normal weave, prints and the selvedge.
3. **Score:** each defect gets 1 to 4 penalty points under the
   [4-point system (ASTM D5430)](skills/fabric-inspection/references/defect-guide.md).
   Holes always score 4.
4. **Grade:** points are normalised per 100 square yards. A is 20 or less, B is up to 40 (the usual buyer
   limit) and C is a reject.
5. **Report:** Gemma 4 writes a short note for the supervisor in Urdu and English, ready to print.

Every photo, result and model name is logged in SQLite, so any grade can be traced back to its evidence.

## How the AI is used (plain language)

Gemma 4 is an open-weight AI model from Google that understands both images and text. We use it twice:

- **As the inspector's eyes.** We send it the photo with instructions that describe each defect type,
  the size scale and what is *not* a defect. It must answer in a fixed JSON format, described in the
  instructions (and enforced with a JSON schema when running offline). Our code then checks that answer, drops low-confidence guesses (below 35%) and does
  the scoring itself. **The model sees; the maths is deterministic.**
- **As the report writer.** We give it the roll summary and defect list, and it writes a three-sentence
  note in Urdu and English. If the model is unavailable, a fixed template writes the note instead, so a
  report always comes out.

### Where Gemma 4 runs: Gemini API first, offline fallback

By default (`BACKEND=auto`) the app calls **Gemma 4 through the Gemini API** (`gemma-4-26b-a4b-it`).
If the API cannot answer (no internet, a bad key, rate limiting, or a reply that is not valid JSON),
the same request goes to **Gemma 4 running on the laptop** through [Ollama](https://ollama.com)
(`gemma4:latest`, 8.1B parameters). A mill floor with patchy Wi-Fi keeps working.

The app always shows which one answered: a blue **Gemini API** badge or a grey **Offline** badge on each
result, a note when it fell back, and a status light in the header (green: Gemini API, amber: offline
only). The model that judged each photo is also saved in the inspection log.

## The Agent Skill

The inspection logic is packaged as an **Agent Skill** following the
[Agent Skills open standard](https://agentskills.io):
[`skills/fabric-inspection/`](skills/fabric-inspection/SKILL.md).

Any compatible AI agent can load it and inspect fabric photos, grade rolls and write reports, using the
bundled scripts or its own vision. **The web app is built on top of the skill:** it imports the skill's
`fabric_core.py`, so the prompt, defect catalogue and grading rules live in one place.

```
skills/fabric-inspection/
├── SKILL.md                    # instructions for the agent
├── references/defect-guide.md  # defect catalogue and 4-point system
└── scripts/
    ├── fabric_core.py          # prompt, schema, parsing, grading (stdlib only)
    ├── inspect_fabric.py       # CLI: photos → defects (Gemma 4 through Ollama)
    └── grade_roll.py           # CLI: defects → roll grade + Urdu/English note
```

## Architecture

```
 Browser (webcam)  ──photo──▶  FastAPI app  ──image + prompt──▶  Gemma 4 via Gemini API
   static/                     app/main.py                            │ fails?
                                    │                                 ▼
                                    │                       Gemma 4 via Ollama (offline)
                                    ├── skills/.../fabric_core.py  (validate, score, grade)
                                    └── SQLite log + saved photos  (data/)
```

## Run it

You need Python 3.10+, a Gemini API key, and [Ollama](https://ollama.com/download) for the offline fallback.

1. Create a Gemini API key in [Google AI Studio](https://aistudio.google.com/apikey).
2. Set up the project:

   ```bash
   cp .env.example .env          # then put your key after GEMINI_API_KEY=
   ollama pull gemma4            # offline fallback: 8.1B, ~9.5 GB. Smaller: gemma4:e2b
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --port 8000
   ```

3. Open <http://localhost:8000> and allow the camera. The header light should be green and say "Gemini API".

`.env` is in `.gitignore`, so your key never goes to GitHub.

### Settings

Set these in `.env`:

| Variable | Default | Meaning |
|---|---|---|
| `BACKEND` | `auto` | `auto` (Gemini API, offline fallback), `gemini` (API only) or `ollama` (offline only) |
| `GEMINI_API_KEY` | | key from [Google AI Studio](https://aistudio.google.com/apikey) |
| `GEMINI_MODEL` | `gemma-4-26b-a4b-it` | Gemma 4 model ID on the Gemini API |
| `OLLAMA_MODEL` | `gemma4:latest` | offline Gemma 4 tag, e.g. `gemma4:e2b` for slower laptops |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server |

### Use the skill from the command line

```bash
cd skills/fabric-inspection
python3 scripts/inspect_fabric.py ../../samples/*.jpg > /tmp/results.jsonl
python3 scripts/grade_roll.py /tmp/results.jsonl --roll R-14 --width-cm 150 --length-m 10
```

### Tests

```bash
pytest
```

## Model, license and dependencies

| What | Version | License |
|---|---|---|
| **Gemma 4** by Google DeepMind, through the Gemini API | `gemma-4-26b-a4b-it` ([docs](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api)) | Apache-2.0, see [ai.google.dev/gemma](https://ai.google.dev/gemma) |
| **Gemma 4**, offline through Ollama | `gemma4:latest`, 8.1B, vision ([ollama.com/library/gemma4](https://ollama.com/library/gemma4)) | Apache-2.0 (run `ollama show gemma4 --license`) |
| Ollama | 0.40+ | MIT |
| FastAPI | see `requirements.txt` | MIT |
| Uvicorn | see `requirements.txt` | BSD-3-Clause |
| httpx | see `requirements.txt` | BSD-3-Clause |
| python-multipart | see `requirements.txt` | Apache-2.0 |
| pytest (tests only) | see `requirements.txt` | MIT |

This project's code is released under the [MIT License](LICENSE).

## Hackathon categories

| Category | How this project fits |
|---|---|
| **Best Open-Source AI Project** (DigitalOcean) | Open-weight Gemma 4 does the core job. MIT-licensed public repo. Ships an Agent Skill. Model, license and dependencies are listed above. |
| **Best Use of Gemma 4** (MLH) | Calls Gemma 4 through the Gemini API. Multimodal: image in, structured defects and Urdu/English text out. A focused tool for a real local industry, with an offline Gemma 4 fallback so the mill floor never stops. |

## Limits and next steps

- Size is estimated from the "photo shows (cm)" setting, so set it to match the camera height.
- It is a decision aid. Inspectors confirm defects before a roll is rejected.
- Next: mount the camera over an inspection table and capture automatically as fabric moves;
  fine-tune on a labelled defect dataset such as TILDA; add Punjabi voice notes through Gemma 4's audio input.

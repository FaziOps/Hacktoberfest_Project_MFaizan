"""SQLite inspection log: every photo, its defects and the model that judged it."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS rolls (
    roll_id TEXT PRIMARY KEY,
    width_cm REAL NOT NULL,
    length_m REAL NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS inspections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    roll_id TEXT NOT NULL REFERENCES rolls(roll_id),
    created_at REAL NOT NULL,
    image_file TEXT NOT NULL,
    result_json TEXT NOT NULL,
    points INTEGER NOT NULL,
    model TEXT NOT NULL,
    latency_ms INTEGER NOT NULL
);
"""


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.images_dir = data_dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = data_dir / "inspections.db"
        with self._connect() as db:
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        return db

    def upsert_roll(self, roll_id: str, width_cm: float, length_m: float) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO rolls (roll_id, width_cm, length_m, created_at) VALUES (?, ?, ?, ?)
                   ON CONFLICT(roll_id) DO UPDATE SET width_cm = excluded.width_cm, length_m = excluded.length_m""",
                (roll_id, width_cm, length_m, time.time()),
            )

    def add_inspection(self, roll_id: str, image: bytes, suffix: str, result: dict, model: str, latency_ms: int) -> int:
        image_file = f"{roll_id}-{time.time_ns()}{suffix}"
        (self.images_dir / image_file).write_bytes(image)
        with self._connect() as db:
            cursor = db.execute(
                """INSERT INTO inspections (roll_id, created_at, image_file, result_json, points, model, latency_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (roll_id, time.time(), image_file, json.dumps(result, ensure_ascii=False), result["points"], model, latency_ms),
            )
            return cursor.lastrowid

    def get_roll(self, roll_id: str) -> dict | None:
        with self._connect() as db:
            roll = db.execute("SELECT * FROM rolls WHERE roll_id = ?", (roll_id,)).fetchone()
            if roll is None:
                return None
            rows = db.execute(
                "SELECT * FROM inspections WHERE roll_id = ? ORDER BY id", (roll_id,)
            ).fetchall()
        inspections = [
            {
                "id": r["id"],
                "created_at": r["created_at"],
                "image_url": f"/images/{r['image_file']}",
                "model": r["model"],
                "latency_ms": r["latency_ms"],
                **json.loads(r["result_json"]),
            }
            for r in rows
        ]
        return {"roll_id": roll_id, "width_cm": roll["width_cm"], "length_m": roll["length_m"], "inspections": inspections}

    def delete_roll(self, roll_id: str) -> None:
        with self._connect() as db:
            files = [r["image_file"] for r in db.execute("SELECT image_file FROM inspections WHERE roll_id = ?", (roll_id,))]
            db.execute("DELETE FROM inspections WHERE roll_id = ?", (roll_id,))
            db.execute("DELETE FROM rolls WHERE roll_id = ?", (roll_id,))
        for name in files:
            (self.images_dir / name).unlink(missing_ok=True)

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .config import DB_PATH, ensure_data_dirs


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    ensure_data_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS plants (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                common_name_ja TEXT,
                scientific_name TEXT,
                aliases_json TEXT NOT NULL DEFAULT '[]',
                description TEXT,
                representative_image_path TEXT,
                first_observed_at TEXT,
                last_observed_at TEXT,
                observation_count INTEGER NOT NULL DEFAULT 0,
                user_corrected INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS observations (
                id TEXT PRIMARY KEY,
                plant_id TEXT,
                status TEXT NOT NULL,
                captured_at TEXT,
                received_at TEXT NOT NULL,
                note TEXT,
                location_label TEXT,
                latitude REAL,
                longitude REAL,
                image1_path TEXT NOT NULL,
                image2_path TEXT NOT NULL,
                image3_path TEXT NOT NULL,
                confidence REAL,
                raw_result_json TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (plant_id) REFERENCES plants(id)
            );

            CREATE TABLE IF NOT EXISTS candidate_names (
                id TEXT PRIMARY KEY,
                observation_id TEXT NOT NULL,
                name TEXT,
                scientific_name TEXT,
                confidence REAL,
                reason TEXT,
                FOREIGN KEY (observation_id) REFERENCES observations(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_plants_scientific_name
                ON plants(scientific_name);
            CREATE INDEX IF NOT EXISTS idx_plants_common_name_ja
                ON plants(common_name_ja);
            CREATE INDEX IF NOT EXISTS idx_observations_plant_id
                ON observations(plant_id);
            """
        )


def create_observation(
    *,
    observation_id: str,
    image_paths: list[Path],
    captured_at: str | None,
    note: str | None,
    location_label: str | None,
    latitude: float | None,
    longitude: float | None,
) -> None:
    timestamp = now_iso()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO observations (
                id, status, captured_at, received_at, note, location_label,
                latitude, longitude, image1_path, image2_path, image3_path,
                created_at, updated_at
            ) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation_id,
                captured_at,
                timestamp,
                note,
                location_label,
                latitude,
                longitude,
                str(image_paths[0]),
                str(image_paths[1]),
                str(image_paths[2]),
                timestamp,
                timestamp,
            ),
        )


def set_observation_status(observation_id: str, status: str, error_message: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE observations
            SET status = ?, error_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, error_message, now_iso(), observation_id),
        )


def get_observation(observation_id: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM observations WHERE id = ?",
            (observation_id,),
        ).fetchone()


def find_or_create_plant(result: dict, representative_image_path: str, observed_at: str | None) -> str:
    common_name = clean_text(result.get("common_name_ja"))
    scientific_name = clean_text(result.get("scientific_name"))
    display_name = common_name or scientific_name or "未確定の植物"
    timestamp = now_iso()
    observed = observed_at or timestamp

    with connect() as conn:
        row = None
        if scientific_name:
            row = conn.execute(
                "SELECT * FROM plants WHERE scientific_name = ? LIMIT 1",
                (scientific_name,),
            ).fetchone()
        if row is None and common_name:
            row = conn.execute(
                "SELECT * FROM plants WHERE common_name_ja = ? LIMIT 1",
                (common_name,),
            ).fetchone()

        if row is not None:
            plant_id = row["id"]
            conn.execute(
                """
                UPDATE plants
                SET display_name = COALESCE(NULLIF(display_name, '未確定の植物'), ?),
                    common_name_ja = COALESCE(common_name_ja, ?),
                    scientific_name = COALESCE(scientific_name, ?),
                    last_observed_at = ?,
                    observation_count = observation_count + 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (display_name, common_name, scientific_name, observed, timestamp, plant_id),
            )
            return plant_id

        plant_id = f"plant-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        conn.execute(
            """
            INSERT INTO plants (
                id, display_name, common_name_ja, scientific_name, aliases_json,
                description, representative_image_path, first_observed_at,
                last_observed_at, observation_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                plant_id,
                display_name,
                common_name,
                scientific_name,
                json.dumps(result.get("aliases", []), ensure_ascii=False),
                clean_text(result.get("care_notes")) or clean_text(result.get("uncertainty_notes")),
                representative_image_path,
                observed,
                observed,
                timestamp,
                timestamp,
            ),
        )
        return plant_id


def save_analysis_result(observation_id: str, result: dict) -> str:
    observation = get_observation(observation_id)
    if observation is None:
        raise ValueError(f"Observation not found: {observation_id}")

    confidence = parse_float(result.get("confidence"))
    status = "analyzed" if confidence is None or confidence >= 0.65 else "needs_review"
    plant_id = find_or_create_plant(
        result,
        observation["image1_path"],
        observation["captured_at"] or observation["received_at"],
    )

    timestamp = now_iso()
    with connect() as conn:
        conn.execute("DELETE FROM candidate_names WHERE observation_id = ?", (observation_id,))
        for idx, candidate in enumerate(result.get("candidates", []) or []):
            conn.execute(
                """
                INSERT INTO candidate_names (
                    id, observation_id, name, scientific_name, confidence, reason
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{observation_id}-candidate-{idx + 1}",
                    observation_id,
                    clean_text(candidate.get("common_name_ja")) or clean_text(candidate.get("name")),
                    clean_text(candidate.get("scientific_name")),
                    parse_float(candidate.get("confidence")),
                    clean_text(candidate.get("reason")),
                ),
            )
        conn.execute(
            """
            UPDATE observations
            SET plant_id = ?, status = ?, confidence = ?, raw_result_json = ?,
                error_message = NULL, updated_at = ?
            WHERE id = ?
            """,
            (
                plant_id,
                status,
                confidence,
                json.dumps(result, ensure_ascii=False),
                timestamp,
                observation_id,
            ),
        )
    return plant_id


def list_plants() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT * FROM plants
            ORDER BY COALESCE(last_observed_at, created_at) DESC
            """
        ).fetchall()


def get_plant(plant_id: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute("SELECT * FROM plants WHERE id = ?", (plant_id,)).fetchone()


def list_observations_for_plant(plant_id: str) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT * FROM observations
            WHERE plant_id = ?
            ORDER BY COALESCE(captured_at, received_at) DESC
            """,
            (plant_id,),
        ).fetchall()


def list_review_observations() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT * FROM observations
            WHERE status IN ('needs_review', 'analysis_failed', 'queued', 'analyzing')
            ORDER BY received_at DESC
            """
        ).fetchall()


def list_recent_observations(limit: int = 20) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT observations.*, plants.display_name AS plant_name
            FROM observations
            LEFT JOIN plants ON observations.plant_id = plants.id
            ORDER BY observations.received_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


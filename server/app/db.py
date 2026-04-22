import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .config import DB_PATH, IMAGE_DIR, ensure_data_dirs


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
                basic_profile_text TEXT,
                visual_appeal_text TEXT,
                care_notes TEXT,
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
                image2_path TEXT,
                image3_path TEXT,
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
        migrate_observation_optional_images(conn)
        migrate_plant_profile_columns(conn)
        migrate_image_paths(conn)
        backfill_plant_profiles(conn)
        normalize_plant_profiles(conn)


def migrate_observation_optional_images(conn: sqlite3.Connection) -> None:
    columns = conn.execute("PRAGMA table_info(observations)").fetchall()
    if not columns:
        return

    notnull_by_name = {column["name"]: column["notnull"] for column in columns}
    if not notnull_by_name.get("image2_path") and not notnull_by_name.get("image3_path"):
        return

    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;

        CREATE TABLE observations_new (
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
            image2_path TEXT,
            image3_path TEXT,
            confidence REAL,
            raw_result_json TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (plant_id) REFERENCES plants(id)
        );

        INSERT INTO observations_new (
            id, plant_id, status, captured_at, received_at, note, location_label,
            latitude, longitude, image1_path, image2_path, image3_path,
            confidence, raw_result_json, error_message, created_at, updated_at
        )
        SELECT
            id, plant_id, status, captured_at, received_at, note, location_label,
            latitude, longitude, image1_path, image2_path, image3_path,
            confidence, raw_result_json, error_message, created_at, updated_at
        FROM observations;

        DROP TABLE observations;
        ALTER TABLE observations_new RENAME TO observations;

        CREATE INDEX IF NOT EXISTS idx_observations_plant_id
            ON observations(plant_id);

        PRAGMA foreign_keys = ON;
        """
    )


def migrate_image_paths(conn: sqlite3.Connection) -> None:
    def normalize_path(value: str | None) -> str | None:
        if not value:
            return value
        path = Path(value)
        parts = path.parts
        for index in range(len(parts) - 1):
            if parts[index].lower() == "images" and index > 0 and parts[index - 1].lower() == "data":
                return str(IMAGE_DIR.joinpath(*parts[index + 1 :]))
        return value

    for table, columns in {
        "observations": ["image1_path", "image2_path", "image3_path"],
        "plants": ["representative_image_path"],
    }.items():
        rows = conn.execute(f"SELECT id, {', '.join(columns)} FROM {table}").fetchall()
        for row in rows:
            updates = {column: normalize_path(row[column]) for column in columns}
            if all(updates[column] == row[column] for column in columns):
                continue
            assignments = ", ".join(f"{column} = ?" for column in columns)
            conn.execute(
                f"UPDATE {table} SET {assignments}, updated_at = ? WHERE id = ?",
                (*[updates[column] for column in columns], now_iso(), row["id"]),
            )


def migrate_plant_profile_columns(conn: sqlite3.Connection) -> None:
    columns = conn.execute("PRAGMA table_info(plants)").fetchall()
    names = {column["name"] for column in columns}
    for name in ["basic_profile_text", "visual_appeal_text", "care_notes"]:
        if name not in names:
            conn.execute(f"ALTER TABLE plants ADD COLUMN {name} TEXT")


def backfill_plant_profiles(conn: sqlite3.Connection) -> None:
    plants = conn.execute(
        """
        SELECT id, basic_profile_text, visual_appeal_text, care_notes
        FROM plants
        WHERE basic_profile_text IS NULL OR visual_appeal_text IS NULL OR care_notes IS NULL
        """
    ).fetchall()
    for plant in plants:
        observation = conn.execute(
            """
            SELECT raw_result_json
            FROM observations
            WHERE plant_id = ? AND raw_result_json IS NOT NULL
            ORDER BY COALESCE(captured_at, received_at) DESC
            LIMIT 1
            """,
            (plant["id"],),
        ).fetchone()
        if not observation:
            continue
        try:
            result = json.loads(observation["raw_result_json"])
        except json.JSONDecodeError:
            continue
        if not isinstance(result, dict):
            continue

        basic = truncate_text(clean_text(plant["basic_profile_text"]) or clean_text(
            result.get("basic_profile_text") or result.get("plant_profile_text")
        ), 120)
        visual = truncate_text(
            clean_text(plant["visual_appeal_text"]) or clean_text(result.get("visual_appeal_text")), 120
        )
        care = truncate_text(clean_text(plant["care_notes"]) or clean_text(result.get("care_notes")), 120)
        if not (basic or visual or care):
            continue
        conn.execute(
            """
            UPDATE plants
            SET basic_profile_text = COALESCE(?, basic_profile_text),
                visual_appeal_text = COALESCE(?, visual_appeal_text),
                care_notes = COALESCE(?, care_notes),
                updated_at = ?
            WHERE id = ?
            """,
            (basic, visual, care, now_iso(), plant["id"]),
        )


def normalize_plant_profiles(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT id, basic_profile_text, visual_appeal_text, care_notes FROM plants"
    ).fetchall()
    for row in rows:
        basic = truncate_text(clean_text(row["basic_profile_text"]), 120)
        visual = truncate_text(clean_text(row["visual_appeal_text"]), 120)
        care = truncate_text(clean_text(row["care_notes"]), 120)
        if (
            basic == row["basic_profile_text"]
            and visual == row["visual_appeal_text"]
            and care == row["care_notes"]
        ):
            continue
        conn.execute(
            """
            UPDATE plants
            SET basic_profile_text = ?,
                visual_appeal_text = ?,
                care_notes = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (basic, visual, care, now_iso(), row["id"]),
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
                str(image_paths[1]) if len(image_paths) > 1 else None,
                str(image_paths[2]) if len(image_paths) > 2 else None,
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


def delete_observation(observation_id: str) -> sqlite3.Row | None:
    observation = get_observation(observation_id)
    if observation is None:
        return None

    plant_id = observation["plant_id"]
    with connect() as conn:
        conn.execute("DELETE FROM observations WHERE id = ?", (observation_id,))

    if plant_id:
        refresh_plant_summary(plant_id)
    return observation


def find_or_create_plant(
    result: dict,
    representative_image_path: str,
    observed_at: str | None,
    *,
    increment_count: bool = True,
    user_corrected: bool = False,
) -> str:
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
            count_delta = 1 if increment_count else 0
            corrected_value = 1 if user_corrected else row["user_corrected"]
            conn.execute(
                """
                UPDATE plants
                SET display_name = CASE WHEN ? = 1 THEN ? ELSE COALESCE(NULLIF(display_name, '未確定の植物'), ?) END,
                    common_name_ja = CASE WHEN ? = 1 THEN ? ELSE COALESCE(common_name_ja, ?) END,
                    scientific_name = CASE WHEN ? = 1 THEN ? ELSE COALESCE(scientific_name, ?) END,
                    last_observed_at = ?,
                    observation_count = observation_count + ?,
                    user_corrected = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    1 if user_corrected else 0,
                    display_name,
                    display_name,
                    1 if user_corrected else 0,
                    common_name,
                    common_name,
                    1 if user_corrected else 0,
                    scientific_name,
                    scientific_name,
                    observed,
                    count_delta,
                    corrected_value,
                    timestamp,
                    plant_id,
                ),
            )
            return plant_id

        plant_id = f"plant-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        conn.execute(
            """
            INSERT INTO plants (
                id, display_name, common_name_ja, scientific_name, aliases_json,
                description, basic_profile_text, visual_appeal_text, care_notes,
                representative_image_path, first_observed_at,
                last_observed_at, observation_count, user_corrected, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plant_id,
                display_name,
                common_name,
                scientific_name,
                json.dumps(result.get("aliases", []), ensure_ascii=False),
                None,
                truncate_text(clean_text(result.get("basic_profile_text")), 120),
                truncate_text(clean_text(result.get("visual_appeal_text")), 120),
                truncate_text(clean_text(result.get("care_notes")), 120),
                representative_image_path,
                observed,
                observed,
                1 if increment_count else 0,
                1 if user_corrected else 0,
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


def update_plant_profile(plant_id: str, profile: dict) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE plants
            SET basic_profile_text = COALESCE(?, basic_profile_text),
                visual_appeal_text = COALESCE(?, visual_appeal_text),
                care_notes = COALESCE(?, care_notes),
                updated_at = ?
            WHERE id = ?
            """,
            (
                truncate_text(clean_text(profile.get("basic_profile_text")), 120),
                truncate_text(clean_text(profile.get("visual_appeal_text")), 120),
                truncate_text(clean_text(profile.get("care_notes")), 120),
                now_iso(),
                plant_id,
            ),
        )


def plant_needs_profile(plant_id: str) -> bool:
    plant = get_plant(plant_id)
    if plant is None:
        return False
    return not (
        clean_text(plant["basic_profile_text"])
        and clean_text(plant["visual_appeal_text"])
        and clean_text(plant["care_notes"])
    )


def update_observation_raw_result(observation_id: str, result: dict) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE observations
            SET raw_result_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (json.dumps(result, ensure_ascii=False), now_iso(), observation_id),
        )


def update_observation_identity_result(observation_id: str, result: dict) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE observations
            SET raw_result_json = ?, confidence = ?, error_message = NULL, updated_at = ?
            WHERE id = ?
            """,
            (
                json.dumps(result, ensure_ascii=False),
                parse_float(result.get("confidence")),
                now_iso(),
                observation_id,
            ),
        )


def apply_manual_correction(
    *,
    observation_id: str,
    common_name_ja: str,
    scientific_name: str | None,
    note: str | None,
    location_label: str | None,
) -> str:
    observation = get_observation(observation_id)
    if observation is None:
        raise ValueError(f"Observation not found: {observation_id}")

    old_plant_id = observation["plant_id"]
    raw_result = {}
    if observation["raw_result_json"]:
        try:
            parsed = json.loads(observation["raw_result_json"])
            if isinstance(parsed, dict):
                raw_result = parsed
        except json.JSONDecodeError:
            raw_result = {}

    raw_result["common_name_ja"] = clean_text(common_name_ja)
    raw_result["scientific_name"] = clean_text(scientific_name)
    raw_result["confidence"] = 1.0
    raw_result["user_corrected"] = True

    corrected_name = raw_result["common_name_ja"] or raw_result["scientific_name"] or "手動修正した植物"
    previous_candidates = raw_result.get("ai_candidates") or raw_result.get("candidates") or []
    if isinstance(previous_candidates, list):
        raw_result["ai_candidates"] = previous_candidates[:3]
    raw_result["candidates"] = [
        {
            "common_name_ja": corrected_name,
            "scientific_name": raw_result["scientific_name"],
            "confidence": 1.0,
            "reason": "手動修正で確定しました。",
        }
    ]

    new_plant_id = find_or_create_plant(
        raw_result,
        observation["image1_path"],
        observation["captured_at"] or observation["received_at"],
        increment_count=False,
        user_corrected=True,
    )

    timestamp = now_iso()
    with connect() as conn:
        conn.execute("DELETE FROM candidate_names WHERE observation_id = ?", (observation_id,))
        conn.execute(
            """
            INSERT INTO candidate_names (
                id, observation_id, name, scientific_name, confidence, reason
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f"{observation_id}-candidate-manual",
                observation_id,
                corrected_name,
                raw_result["scientific_name"],
                1.0,
                "手動修正で確定しました。",
            ),
        )
        conn.execute(
            """
            UPDATE observations
            SET plant_id = ?, status = 'analyzed', confidence = 1.0,
                raw_result_json = ?, note = ?, location_label = ?,
                error_message = NULL, updated_at = ?
            WHERE id = ?
            """,
            (
                new_plant_id,
                json.dumps(raw_result, ensure_ascii=False),
                clean_text(note),
                clean_text(location_label),
                timestamp,
                observation_id,
            ),
        )

    refresh_plant_summary(new_plant_id)
    if old_plant_id and old_plant_id != new_plant_id:
        refresh_plant_summary(old_plant_id)
    return new_plant_id


def refresh_plant_summary(plant_id: str) -> None:
    with connect() as conn:
        summary = conn.execute(
            """
            SELECT
                COUNT(*) AS observation_count,
                MIN(COALESCE(captured_at, received_at)) AS first_observed_at,
                MAX(COALESCE(captured_at, received_at)) AS last_observed_at
            FROM observations
            WHERE plant_id = ?
            """,
            (plant_id,),
        ).fetchone()
        if summary is None or summary["observation_count"] == 0:
            conn.execute("DELETE FROM plants WHERE id = ?", (plant_id,))
            return

        representative = conn.execute(
            """
            SELECT image1_path
            FROM observations
            WHERE plant_id = ?
            ORDER BY COALESCE(captured_at, received_at) DESC
            LIMIT 1
            """,
            (plant_id,),
        ).fetchone()
        conn.execute(
            """
            UPDATE plants
            SET observation_count = ?,
                first_observed_at = ?,
                last_observed_at = ?,
                representative_image_path = COALESCE(?, representative_image_path),
                updated_at = ?
            WHERE id = ?
            """,
            (
                summary["observation_count"],
                summary["first_observed_at"],
                summary["last_observed_at"],
                representative["image1_path"] if representative else None,
                now_iso(),
                plant_id,
            ),
        )


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


def list_recent_image_paths_for_plant(plant_id: str, limit: int = 12) -> list[str]:
    paths: list[str] = []
    observations = list_observations_for_plant(plant_id)
    for observation in observations:
        for key in ["image1_path", "image2_path", "image3_path"]:
            path = observation[key]
            if path:
                paths.append(path)
            if len(paths) >= limit:
                return paths
    return paths


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


def list_observations() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT observations.*, plants.display_name AS plant_name
            FROM observations
            LEFT JOIN plants ON observations.plant_id = plants.id
            ORDER BY COALESCE(observations.captured_at, observations.received_at) DESC
            """
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


def truncate_text(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip("、。,. ") + "…"

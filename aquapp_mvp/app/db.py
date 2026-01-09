from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "db" / "aquapp.sqlite"

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS photos (
                id TEXT PRIMARY KEY,
                created_at TEXT,
                source TEXT,
                filename TEXT,
                filepath TEXT,
                content_type TEXT,
                user_comment TEXT
            );
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                photo_id TEXT,
                created_at TEXT,
                model TEXT,
                json_text TEXT,
                raw_text TEXT,
                success INTEGER,
                FOREIGN KEY(photo_id) REFERENCES photos(id)
            );
            """
        )
        if not _column_exists(conn, "photos", "user_comment"):
            conn.execute("ALTER TABLE photos ADD COLUMN user_comment TEXT")
        conn.commit()
        logger.info("Database initialized at %s", DB_PATH)
    finally:
        conn.close()

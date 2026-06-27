from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from jobos.config import DATA_DIR
from jobos.schemas import TrackerRecord

DB_PATH = DATA_DIR / "applications.db"


def init_db(db_path: Path = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT,
                role_title TEXT,
                job_url TEXT,
                platform TEXT,
                fit_score INTEGER,
                category TEXT,
                status TEXT,
                cv_version TEXT,
                cover_letter_version TEXT,
                created_at TEXT,
                submitted_at TEXT,
                follow_up_date TEXT,
                notes TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id INTEGER,
                question TEXT,
                answer TEXT,
                confidence TEXT,
                risk_level TEXT,
                FOREIGN KEY(application_id) REFERENCES applications(id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def save_application(record: TrackerRecord, db_path: Path = DB_PATH) -> int:
    init_db(db_path)
    created_at = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO applications (
                company, role_title, job_url, platform, fit_score, category,
                status, cv_version, cover_letter_version, created_at, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.company,
                record.role_title,
                record.job_url,
                record.platform,
                record.fit_score,
                record.category,
                record.status,
                record.cv_version,
                record.cover_letter_version,
                created_at,
                record.notes,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()

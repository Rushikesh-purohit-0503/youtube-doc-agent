import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DB_PATH = os.getenv("DB_PATH", "/app/db/history.db")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id           TEXT PRIMARY KEY,
                job_id       TEXT NOT NULL,
                title        TEXT NOT NULL,
                thumbnail_url TEXT,
                pdf_path     TEXT,
                created_at   TEXT NOT NULL
            )
            """
        )


def save_to_history(
    doc_id: str,
    job_id: str,
    title: str,
    thumbnail_url: str,
    pdf_path: str,
) -> None:
    _init()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO history (id, job_id, title, thumbnail_url, pdf_path, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (doc_id, job_id, title, thumbnail_url, pdf_path, datetime.now(timezone.utc).isoformat()),
        )


def get_history() -> List[Dict[str, Any]]:
    _init()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, job_id, title, thumbnail_url, created_at "
            "FROM history ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_from_history(doc_id: str) -> None:
    _init()
    with _connect() as conn:
        row = conn.execute(
            "SELECT pdf_path FROM history WHERE id = ?", (doc_id,)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM history WHERE id = ?", (doc_id,))
            pdf_path: Optional[str] = row["pdf_path"]
            if pdf_path and os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                except OSError:
                    pass

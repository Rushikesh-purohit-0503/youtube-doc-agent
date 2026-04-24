import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.db import get_connection


def save_to_history(
    doc_id: str,
    job_id: str,
    title: str,
    thumbnail_url: str,
    pdf_path: str,
    user_id: Optional[str] = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO history (id, job_id, title, thumbnail_url, pdf_path, created_at, user_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (doc_id, job_id, title, thumbnail_url, pdf_path,
             datetime.now(timezone.utc).isoformat(), user_id),
        )


def get_history() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, job_id, title, thumbnail_url, created_at "
            "FROM history ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_from_history(doc_id: str) -> None:
    with get_connection() as conn:
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

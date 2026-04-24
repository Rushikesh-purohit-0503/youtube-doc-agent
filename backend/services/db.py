import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "/app/db/history.db")


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            TEXT PRIMARY KEY,
                email         TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                plan          TEXT NOT NULL DEFAULT 'free',
                created_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                id                TEXT PRIMARY KEY,
                user_id           TEXT NOT NULL REFERENCES users(id),
                plan              TEXT NOT NULL,
                rc_original_tx_id TEXT,
                rc_product_id     TEXT,
                started_at        TEXT NOT NULL,
                expires_at        TEXT,
                is_active         INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS usage (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT NOT NULL REFERENCES users(id),
                job_id     TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS history (
                id            TEXT PRIMARY KEY,
                job_id        TEXT NOT NULL,
                title         TEXT NOT NULL,
                thumbnail_url TEXT,
                pdf_path      TEXT,
                created_at    TEXT NOT NULL,
                user_id       TEXT REFERENCES users(id)
            );
        """)
        # Migrate existing history table if user_id column is missing
        try:
            conn.execute("ALTER TABLE history ADD COLUMN user_id TEXT REFERENCES users(id)")
        except Exception:
            pass  # column already exists

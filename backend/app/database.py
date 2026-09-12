import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "users.db"

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    conn = get_conn()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS allowed_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL COLLATE NOCASE)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL COLLATE NOCASE,
            phone TEXT, address TEXT, extra_data TEXT)""")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "city" in columns and "address" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN address TEXT")
            conn.execute("UPDATE users SET address = city WHERE address IS NULL")
        if "extra_data" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN extra_data TEXT")
        conn.commit()
    finally:
        conn.close()

def seed_admins() -> None:
    conn = get_conn()
    try:
        for email in ("admin@example.com", "test06.wpbrigade@gmail.com"):
            conn.execute("INSERT OR IGNORE INTO allowed_emails(email) VALUES (?)", (email.lower(),))
        conn.commit()
    finally: conn.close()

def is_allowed_email(email: str) -> bool:
    conn = get_conn()
    try:
        return conn.execute("SELECT 1 FROM allowed_emails WHERE email = ? COLLATE NOCASE",
                            (email.strip(),)).fetchone() is not None
    finally: conn.close()

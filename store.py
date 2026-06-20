"""
store.py — قاعدة بيانات SQLite دائمة.
تخزن: المشاريع + ملفاتها بشكل دائم 100% (تنجو من إعادة تشغيل Render).
"""
import os
import sqlite3
import json
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                files TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, name)
            )
        """)


init_db()


def add_project(user_id: str, name: str, url: str, files: list = None):
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO projects (user_id, name, url, files) VALUES (?, ?, ?, ?)",
            (str(user_id), name, url, json.dumps(files or []))
        )


def get_projects(user_id: str) -> list:
    with _conn() as c:
        rows = c.execute(
            "SELECT name, url FROM projects WHERE user_id = ? ORDER BY created_at DESC",
            (str(user_id),)
        ).fetchall()
        return [{"name": r["name"], "url": r["url"]} for r in rows]


def get_project_files_db(user_id: str, name: str) -> list:
    with _conn() as c:
        row = c.execute(
            "SELECT files FROM projects WHERE user_id = ? AND name = ?",
            (str(user_id), name)
        ).fetchone()
        return json.loads(row["files"]) if row else []


def delete_project(user_id: str, name: str):
    with _conn() as c:
        c.execute("DELETE FROM projects WHERE user_id = ? AND name = ?", (str(user_id), name))


def get_all_projects() -> list:
    """يستخدمه server.py لاسترجاع كل المواقع على القرص بعد كل إعادة تشغيل."""
    with _conn() as c:
        rows = c.execute("SELECT user_id, name, url, files FROM projects").fetchall()
        return [
            {"user_id": r["user_id"], "name": r["name"], "url": r["url"], "files": json.loads(r["files"])}
            for r in rows
        ]


def project_exists(user_id: str, name: str) -> bool:
    with _conn() as c:
        row = c.execute(
            "SELECT 1 FROM projects WHERE user_id = ? AND name = ?",
            (str(user_id), name)
        ).fetchone()
        return row is not None

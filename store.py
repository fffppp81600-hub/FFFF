"""
store.py — قاعدة بيانات SQLite دائمة.
تخزن: المشاريع وملفاتها + الصور المرفوعة (base64) بشكل دائم 100%.
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
        c.execute("""
            CREATE TABLE IF NOT EXISTS images (
                project_name TEXT NOT NULL,
                filename TEXT NOT NULL,
                b64_data TEXT NOT NULL,
                mime TEXT DEFAULT 'image/jpeg',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (project_name, filename)
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
        c.execute("DELETE FROM images WHERE project_name = ?", (name,))


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


# ── Images (دائمة 100% — base64 بقاعدة البيانات) ──────────
def save_image(project_name: str, filename: str, b64_data: str, mime: str = "image/jpeg"):
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO images (project_name, filename, b64_data, mime) VALUES (?, ?, ?, ?)",
            (project_name, filename, b64_data, mime)
        )


def get_image(project_name: str, filename: str):
    with _conn() as c:
        row = c.execute(
            "SELECT b64_data, mime FROM images WHERE project_name = ? AND filename = ?",
            (project_name, filename)
        ).fetchone()
        return (row["b64_data"], row["mime"]) if row else None


def get_all_images() -> list:
    """يستخدمه server.py لاسترجاع كل الصور المرفوعة على القرص بعد كل إعادة تشغيل."""
    with _conn() as c:
        rows = c.execute("SELECT project_name, filename, b64_data, mime FROM images").fetchall()
        return [dict(r) for r in rows]

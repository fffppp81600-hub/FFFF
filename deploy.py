"""
store.py — قاعدة بيانات SQLite محلية دائمة.
تخزن: المشاريع وملفاتها + الصور المرفوعة (base64) — يُسترجَع كل شيء تلقائياً
على القرص بعد كل إعادة تشغيل عبر restore_all_sites_from_db() في deploy.py.
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
                display_name TEXT,
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
        try:
            c.execute("ALTER TABLE projects ADD COLUMN display_name TEXT")
        except sqlite3.OperationalError:
            pass  # العمود موجود فعلاً


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
            "SELECT name, url, display_name FROM projects WHERE user_id = ? ORDER BY created_at DESC",
            (str(user_id),)
        ).fetchall()
        return [
            {"name": r["name"], "url": r["url"], "display_name": r["display_name"] or r["name"]}
            for r in rows
        ]


def rename_project(user_id: str, name: str, new_display_name: str) -> bool:
    """يغيّر الاسم التعريفي فقط — لا يؤثر على رابط الموقع الفعلي."""
    with _conn() as c:
        cur = c.execute(
            "UPDATE projects SET display_name = ? WHERE user_id = ? AND name = ?",
            (new_display_name.strip(), str(user_id), name)
        )
        return cur.rowcount > 0


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
    with _conn() as c:
        rows = c.execute("SELECT project_name, filename, b64_data, mime FROM images").fetchall()
        return [dict(r) for r in rows]

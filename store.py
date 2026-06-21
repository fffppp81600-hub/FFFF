"""
store.py — قاعدة بيانات Turso (libSQL) سحابية، باستخدام مكتبة libsql الجديدة
(المكتبة القديمة libsql-client تعتمد WebSocket وتوقفت رسمياً بتاريخ 18 يونيو 2026
بعد انتقال Turso من Fly.io إلى AWS — السبب الحقيقي لخطأ WSServerHandshakeError).

الإعداد المطلوب بمتغيرات البيئة (موجود عندك فعلاً بـ Render):
    TURSO_DATABASE_URL = libsql://اسم-قاعدتك.turso.io
    TURSO_AUTH_TOKEN   = التوكن من لوحة Turso
"""
import os
import json
import libsql

TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "").strip()
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "").strip()

if not TURSO_DATABASE_URL or not TURSO_AUTH_TOKEN:
    raise RuntimeError(
        "لازم تضبط TURSO_DATABASE_URL و TURSO_AUTH_TOKEN بمتغيرات البيئة "
        "(من لوحة https://turso.tech)!"
    )

_conn = libsql.connect(database=TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN)


def init_db():
    _conn.execute("""
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
    _conn.execute("""
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
        _conn.execute("ALTER TABLE projects ADD COLUMN display_name TEXT")
    except Exception:
        pass  # العمود موجود فعلاً
    _conn.commit()


init_db()


def add_project(user_id: str, name: str, url: str, files: list = None):
    _conn.execute(
        "INSERT OR REPLACE INTO projects (user_id, name, url, files) VALUES (?, ?, ?, ?)",
        [str(user_id), name, url, json.dumps(files or [])]
    )
    _conn.commit()


def get_projects(user_id: str) -> list:
    rows = _conn.execute(
        "SELECT name, url, display_name FROM projects WHERE user_id = ? ORDER BY created_at DESC",
        [str(user_id)]
    ).fetchall()
    return [
        {"name": r[0], "url": r[1], "display_name": r[2] or r[0]}
        for r in rows
    ]


def rename_project(user_id: str, name: str, new_display_name: str) -> bool:
    cur = _conn.execute(
        "UPDATE projects SET display_name = ? WHERE user_id = ? AND name = ?",
        [new_display_name.strip(), str(user_id), name]
    )
    _conn.commit()
    return True


def get_project_files_db(user_id: str, name: str) -> list:
    rows = _conn.execute(
        "SELECT files FROM projects WHERE user_id = ? AND name = ?",
        [str(user_id), name]
    ).fetchall()
    return json.loads(rows[0][0]) if rows else []


def delete_project(user_id: str, name: str):
    _conn.execute("DELETE FROM projects WHERE user_id = ? AND name = ?", [str(user_id), name])
    _conn.execute("DELETE FROM images WHERE project_name = ?", [name])
    _conn.commit()


def get_all_projects() -> list:
    rows = _conn.execute("SELECT user_id, name, url, files FROM projects").fetchall()
    return [
        {"user_id": r[0], "name": r[1], "url": r[2], "files": json.loads(r[3])}
        for r in rows
    ]


def project_exists(user_id: str, name: str) -> bool:
    rows = _conn.execute(
        "SELECT 1 FROM projects WHERE user_id = ? AND name = ?",
        [str(user_id), name]
    ).fetchall()
    return len(rows) > 0


def save_image(project_name: str, filename: str, b64_data: str, mime: str = "image/jpeg"):
    _conn.execute(
        "INSERT OR REPLACE INTO images (project_name, filename, b64_data, mime) VALUES (?, ?, ?, ?)",
        [project_name, filename, b64_data, mime]
    )
    _conn.commit()


def get_image(project_name: str, filename: str):
    rows = _conn.execute(
        "SELECT b64_data, mime FROM images WHERE project_name = ? AND filename = ?",
        [project_name, filename]
    ).fetchall()
    return (rows[0][0], rows[0][1]) if rows else None


def get_all_images() -> list:
    rows = _conn.execute("SELECT project_name, filename, b64_data, mime FROM images").fetchall()
    return [
        {"project_name": r[0], "filename": r[1], "b64_data": r[2], "mime": r[3]}
        for r in rows
    ]

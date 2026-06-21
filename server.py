"""
store.py — قاعدة بيانات Turso (libSQL) سحابية حقيقية، مستقلة عن قرص Render.
تخزن: المشاريع وملفاتها + الصور المرفوعة (base64) بشكل دائم 100% — حتى بعد أي
إعادة تشغيل أو redeploy على Render (القرص المحلي وSQLite المحلي القديم كانا يُمسحان
بالكامل عند كل إعادة تشغيل على الخطة المجانية؛ هذا الملف صار يعتمد بالكامل على
قاعدة بيانات خارجية حقيقية بدل ملف SQLite محلي).

الإعداد المطلوب بمتغيرات البيئة (Render → Environment):
  TURSO_DATABASE_URL = libsql://اسم-قاعدتك.turso.io
  TURSO_AUTH_TOKEN   = التوكن من لوحة Turso

ملاحظة مهمة: كل دوال هذا الملف بنفس الاسم وبنفس شكل المُخرجات تماماً كالنسخة القديمة
(القائمة على sqlite3 المحلي)، فلا يحتاج أي ملف آخر (bot.py / deploy.py / file_manager.py
/ server.py) أي تعديل — الاستبدال محصور هنا بالكامل.
"""
import os
import json
import libsql_client

TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")

if not TURSO_DATABASE_URL or not TURSO_AUTH_TOKEN:
    raise RuntimeError(
        "لازم تضبط TURSO_DATABASE_URL و TURSO_AUTH_TOKEN بمتغيرات البيئة "
        "(أنشئ قاعدة بيانات مجانية من https://turso.tech وخذ القيمتين من لوحتها)!"
    )

_client = libsql_client.create_client_sync(url=TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN)


def init_db():
    _client.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            files TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, name)
        )
    """)
    _client.execute("""
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
    _client.execute(
        "INSERT OR REPLACE INTO projects (user_id, name, url, files) VALUES (?, ?, ?, ?)",
        [str(user_id), name, url, json.dumps(files or [])]
    )


def get_projects(user_id: str) -> list:
    rs = _client.execute(
        "SELECT name, url FROM projects WHERE user_id = ? ORDER BY created_at DESC",
        [str(user_id)]
    )
    return [{"name": r["name"], "url": r["url"]} for r in rs.rows]


def get_project_files_db(user_id: str, name: str) -> list:
    rs = _client.execute(
        "SELECT files FROM projects WHERE user_id = ? AND name = ?",
        [str(user_id), name]
    )
    return json.loads(rs.rows[0]["files"]) if rs.rows else []


def delete_project(user_id: str, name: str):
    _client.execute("DELETE FROM projects WHERE user_id = ? AND name = ?", [str(user_id), name])
    _client.execute("DELETE FROM images WHERE project_name = ?", [name])


def get_all_projects() -> list:
    """يستخدمه server.py لاسترجاع كل المواقع على القرص بعد كل إعادة تشغيل."""
    rs = _client.execute("SELECT user_id, name, url, files FROM projects")
    return [
        {"user_id": r["user_id"], "name": r["name"], "url": r["url"], "files": json.loads(r["files"])}
        for r in rs.rows
    ]


def project_exists(user_id: str, name: str) -> bool:
    rs = _client.execute(
        "SELECT 1 FROM projects WHERE user_id = ? AND name = ?",
        [str(user_id), name]
    )
    return len(rs.rows) > 0


# ── Images (دائمة 100% — base64 بقاعدة بيانات Turso الخارجية) ──────────
def save_image(project_name: str, filename: str, b64_data: str, mime: str = "image/jpeg"):
    _client.execute(
        "INSERT OR REPLACE INTO images (project_name, filename, b64_data, mime) VALUES (?, ?, ?, ?)",
        [project_name, filename, b64_data, mime]
    )


def get_image(project_name: str, filename: str):
    rs = _client.execute(
        "SELECT b64_data, mime FROM images WHERE project_name = ? AND filename = ?",
        [project_name, filename]
    )
    return (rs.rows[0]["b64_data"], rs.rows[0]["mime"]) if rs.rows else None


def get_all_images() -> list:
    """يستخدمه server.py لاسترجاع كل الصور المرفوعة على القرص بعد كل إعادة تشغيل."""
    rs = _client.execute("SELECT project_name, filename, b64_data, mime FROM images")
    return [
        {
            "project_name": r["project_name"],
            "filename": r["filename"],
            "b64_data": r["b64_data"],
            "mime": r["mime"],
        }
        for r in rs.rows
    ]

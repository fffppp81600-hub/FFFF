"""
store.py — قاعدة بيانات Turso (libSQL) سحابية — النسخة المطورة.

جداول:
  - users       : معلومات المستخدمين + إحصائيات
  - projects    : المشاريع (اسم، رابط، ملفات، نوع)
  - versions    : كل نسخة من كل مشروع (Version Control كامل)
  - assets      : الصور والملفات المرفوعة
  - sessions    : جلسات محادثة التخطيط (ذاكرة دائمة بين التشغيلات)
"""
import os
import json
import libsql
from logger import log

TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "").strip()
TURSO_AUTH_TOKEN   = os.getenv("TURSO_AUTH_TOKEN", "").strip()

if not TURSO_DATABASE_URL or not TURSO_AUTH_TOKEN:
    raise RuntimeError(
        "لازم تضبط TURSO_DATABASE_URL و TURSO_AUTH_TOKEN بمتغيرات البيئة!"
    )

_conn = libsql.connect(database=TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN)


# ══════════════════════════════════════════════
# تهيئة قاعدة البيانات
# ══════════════════════════════════════════════
def init_db():
    # جدول المستخدمين
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id      TEXT PRIMARY KEY,
            username     TEXT,
            first_name   TEXT,
            builds_count INTEGER DEFAULT 0,
            edits_count  INTEGER DEFAULT 0,
            images_count INTEGER DEFAULT 0,
            last_active  TEXT DEFAULT CURRENT_TIMESTAMP,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # جدول المشاريع
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            user_id      TEXT NOT NULL,
            name         TEXT NOT NULL,
            url          TEXT NOT NULL,
            files        TEXT NOT NULL DEFAULT '[]',
            display_name TEXT,
            project_type TEXT DEFAULT 'website',
            description  TEXT DEFAULT '',
            version_num  INTEGER DEFAULT 1,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, name)
        )
    """)

    # جدول الإصدارات (Version Control)
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS versions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      TEXT NOT NULL,
            project_name TEXT NOT NULL,
            version_num  INTEGER NOT NULL,
            files        TEXT NOT NULL,
            description  TEXT DEFAULT '',
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # جدول الأصول (Assets)
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT NOT NULL,
            user_id      TEXT NOT NULL,
            filename     TEXT NOT NULL,
            b64_data     TEXT NOT NULL,
            mime         TEXT DEFAULT 'image/jpeg',
            url          TEXT DEFAULT '',
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_name, filename)
        )
    """)

    # جدول الجلسات (ذاكرة المحادثة الدائمة)
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            user_id      TEXT PRIMARY KEY,
            history      TEXT NOT NULL DEFAULT '[]',
            current_proj TEXT DEFAULT '',
            updated_at   TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # جدول الصور القديم للتوافق
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS images (
            project_name TEXT NOT NULL,
            filename     TEXT NOT NULL,
            b64_data     TEXT NOT NULL,
            mime         TEXT DEFAULT 'image/jpeg',
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (project_name, filename)
        )
    """)

    # إضافة أعمدة جديدة لو ما كانت موجودة (ترقية آمنة)
    _safe_alter("projects", "display_name", "TEXT")
    _safe_alter("projects", "project_type", "TEXT DEFAULT 'website'")
    _safe_alter("projects", "description",  "TEXT DEFAULT ''")
    _safe_alter("projects", "version_num",  "INTEGER DEFAULT 1")
    _safe_alter("projects", "updated_at",   "TEXT DEFAULT CURRENT_TIMESTAMP")

    _conn.commit()
    log("[DB_INIT] قاعدة البيانات جاهزة")


def _safe_alter(table: str, column: str, col_type: str):
    try:
        _conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        _conn.commit()
    except Exception:
        pass  # العمود موجود فعلاً


init_db()


# ══════════════════════════════════════════════
# المستخدمون
# ══════════════════════════════════════════════
def upsert_user(user_id: str, username: str = "", first_name: str = ""):
    _conn.execute("""
        INSERT INTO users (user_id, username, first_name, last_active)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            username    = excluded.username,
            first_name  = excluded.first_name,
            last_active = CURRENT_TIMESTAMP
    """, [str(user_id), username or "", first_name or ""])
    _conn.commit()


def increment_user_stat(user_id: str, stat: str):
    """stat: builds_count | edits_count | images_count"""
    allowed = {"builds_count", "edits_count", "images_count"}
    if stat not in allowed:
        return
    _conn.execute(
        f"UPDATE users SET {stat} = {stat} + 1, last_active = CURRENT_TIMESTAMP WHERE user_id = ?",
        [str(user_id)]
    )
    _conn.commit()


def get_user_stats(user_id: str) -> dict:
    rows = _conn.execute(
        "SELECT builds_count, edits_count, images_count, last_active FROM users WHERE user_id = ?",
        [str(user_id)]
    ).fetchall()
    if not rows:
        return {"builds": 0, "edits": 0, "images": 0, "last_active": "—"}
    r = rows[0]
    return {"builds": r[0], "edits": r[1], "images": r[2], "last_active": r[3]}


# ══════════════════════════════════════════════
# المشاريع
# ══════════════════════════════════════════════
def add_project(user_id: str, name: str, url: str, files: list = None,
                project_type: str = "website", description: str = ""):
    files_json = json.dumps(files or [])
    _conn.execute("""
        INSERT OR REPLACE INTO projects
            (user_id, name, url, files, project_type, description, version_num, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
    """, [str(user_id), name, url, files_json, project_type, description])
    _conn.commit()


def get_projects(user_id: str) -> list:
    rows = _conn.execute("""
        SELECT name, url, display_name, project_type, version_num, updated_at
        FROM projects WHERE user_id = ? ORDER BY updated_at DESC
    """, [str(user_id)]).fetchall()
    return [
        {
            "name": r[0],
            "url":  r[1],
            "display_name": r[2] or r[0],
            "project_type": r[3] or "website",
            "version_num":  r[4] or 1,
            "updated_at":   r[5] or "",
        }
        for r in rows
    ]


def rename_project(user_id: str, name: str, new_display_name: str) -> bool:
    _conn.execute(
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
    _conn.execute("DELETE FROM versions WHERE user_id = ? AND project_name = ?", [str(user_id), name])
    _conn.execute("DELETE FROM assets WHERE user_id = ? AND project_name = ?", [str(user_id), name])
    _conn.execute("DELETE FROM images WHERE project_name = ?", [name])
    _conn.commit()


def get_all_projects() -> list:
    rows = _conn.execute(
        "SELECT user_id, name, url, files FROM projects"
    ).fetchall()
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


def update_project_files(user_id: str, name: str, files: list, url: str = ""):
    """تحديث ملفات مشروع موجود + رفع رقم الإصدار."""
    if url:
        _conn.execute("""
            UPDATE projects SET files = ?, url = ?, version_num = version_num + 1,
            updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND name = ?
        """, [json.dumps(files), url, str(user_id), name])
    else:
        _conn.execute("""
            UPDATE projects SET files = ?, version_num = version_num + 1,
            updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND name = ?
        """, [json.dumps(files), str(user_id), name])
    _conn.commit()


# ══════════════════════════════════════════════
# Version Control
# ══════════════════════════════════════════════
def save_version(user_id: str, project_name: str, files: list, description: str = "") -> int:
    """يحفظ نسخة جديدة — يرجع رقم الإصدار."""
    rows = _conn.execute("""
        SELECT COALESCE(MAX(version_num), 0) FROM versions
        WHERE user_id = ? AND project_name = ?
    """, [str(user_id), project_name]).fetchall()
    next_ver = (rows[0][0] if rows else 0) + 1

    _conn.execute("""
        INSERT INTO versions (user_id, project_name, version_num, files, description)
        VALUES (?, ?, ?, ?, ?)
    """, [str(user_id), project_name, next_ver, json.dumps(files), description])
    _conn.commit()
    log(f"[VERSION_SAVED] proj={project_name} ver={next_ver}")
    return next_ver


def get_versions(user_id: str, project_name: str) -> list:
    """قائمة كل الإصدارات (بدون الملفات الضخمة)."""
    rows = _conn.execute("""
        SELECT version_num, description, created_at FROM versions
        WHERE user_id = ? AND project_name = ?
        ORDER BY version_num DESC
    """, [str(user_id), project_name]).fetchall()
    return [{"version": r[0], "description": r[1], "created_at": r[2]} for r in rows]


def get_version_files(user_id: str, project_name: str, version_num: int) -> list:
    """يرجع ملفات إصدار محدد."""
    rows = _conn.execute("""
        SELECT files FROM versions
        WHERE user_id = ? AND project_name = ? AND version_num = ?
    """, [str(user_id), project_name, version_num]).fetchall()
    return json.loads(rows[0][0]) if rows else []


def get_latest_version_num(user_id: str, project_name: str) -> int:
    rows = _conn.execute("""
        SELECT COALESCE(MAX(version_num), 0) FROM versions
        WHERE user_id = ? AND project_name = ?
    """, [str(user_id), project_name]).fetchall()
    return rows[0][0] if rows else 0


def delete_old_versions(user_id: str, project_name: str, keep: int = 10):
    """يحتفظ بآخر N نسخة فقط لتوفير مساحة."""
    _conn.execute("""
        DELETE FROM versions WHERE user_id = ? AND project_name = ?
        AND version_num NOT IN (
            SELECT version_num FROM versions
            WHERE user_id = ? AND project_name = ?
            ORDER BY version_num DESC LIMIT ?
        )
    """, [str(user_id), project_name, str(user_id), project_name, keep])
    _conn.commit()


# ══════════════════════════════════════════════
# Assets (الأصول)
# ══════════════════════════════════════════════
def save_asset(project_name: str, user_id: str, filename: str,
               b64_data: str, mime: str = "image/jpeg", url: str = ""):
    _conn.execute("""
        INSERT OR REPLACE INTO assets (project_name, user_id, filename, b64_data, mime, url)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [project_name, str(user_id), filename, b64_data, mime, url])
    _conn.commit()


def get_asset(project_name: str, filename: str):
    rows = _conn.execute(
        "SELECT b64_data, mime, url FROM assets WHERE project_name = ? AND filename = ?",
        [project_name, filename]
    ).fetchall()
    return {"b64": rows[0][0], "mime": rows[0][1], "url": rows[0][2]} if rows else None


def get_project_assets(project_name: str) -> list:
    rows = _conn.execute(
        "SELECT filename, mime, url, created_at FROM assets WHERE project_name = ?",
        [project_name]
    ).fetchall()
    return [{"filename": r[0], "mime": r[1], "url": r[2], "created_at": r[3]} for r in rows]


def get_all_assets() -> list:
    rows = _conn.execute(
        "SELECT project_name, user_id, filename, b64_data, mime FROM assets"
    ).fetchall()
    return [
        {"project_name": r[0], "user_id": r[1], "filename": r[2], "b64_data": r[3], "mime": r[4]}
        for r in rows
    ]


# ══════════════════════════════════════════════
# الجلسات (ذاكرة دائمة)
# ══════════════════════════════════════════════
def save_session(user_id: str, history: list, current_proj: str = ""):
    _conn.execute("""
        INSERT OR REPLACE INTO sessions (user_id, history, current_proj, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    """, [str(user_id), json.dumps(history[-20:]), current_proj])  # آخر 20 رسالة فقط
    _conn.commit()


def get_session(user_id: str) -> dict:
    rows = _conn.execute(
        "SELECT history, current_proj FROM sessions WHERE user_id = ?",
        [str(user_id)]
    ).fetchall()
    if not rows:
        return {"history": [], "current_proj": ""}
    return {"history": json.loads(rows[0][0]), "current_proj": rows[0][1] or ""}


def clear_session(user_id: str):
    _conn.execute("DELETE FROM sessions WHERE user_id = ?", [str(user_id)])
    _conn.commit()


# ══════════════════════════════════════════════
# الصور (للتوافق مع الكود القديم)
# ══════════════════════════════════════════════
def save_image(project_name: str, filename: str, b64_data: str, mime: str = "image/jpeg"):
    _conn.execute("""
        INSERT OR REPLACE INTO images (project_name, filename, b64_data, mime)
        VALUES (?, ?, ?, ?)
    """, [project_name, filename, b64_data, mime])
    _conn.commit()


def get_image(project_name: str, filename: str):
    rows = _conn.execute(
        "SELECT b64_data, mime FROM images WHERE project_name = ? AND filename = ?",
        [project_name, filename]
    ).fetchall()
    return (rows[0][0], rows[0][1]) if rows else None


def get_all_images() -> list:
    rows = _conn.execute(
        "SELECT project_name, filename, b64_data, mime FROM images"
    ).fetchall()
    return [
        {"project_name": r[0], "filename": r[1], "b64_data": r[2], "mime": r[3]}
        for r in rows
    ]

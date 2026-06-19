"""
file_manager.py — إدارة ملفات المشاريع على القرص المحلي.
يتعامل مع: /projects/<user_id>/<project_name>/ (مساحة عمل Claude/AI المحلية قبل النشر)

ميزات:
  - قراءة/حذف ملفات مشروع
  - فحص سلامة المشروع (الملفات الأساسية موجودة وغير فاضية)
  - حساب حجم المشروع
  - نسخ احتياطي تلقائي قبل أي حذف (للأمان)
"""
import os
import shutil
from datetime import datetime
from logger import log, log_warn, log_error

PROJECTS_DIR = os.path.join(os.path.dirname(__file__), "projects")
BACKUP_DIR   = os.path.join(os.path.dirname(__file__), "_backups")
os.makedirs(PROJECTS_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

REQUIRED_FILES = {"index.html", "style.css", "script.js"}


def _project_path(user_id: str, project_name: str) -> str:
    return os.path.join(PROJECTS_DIR, str(user_id), project_name)


def get_project_files(user_id: str, project_name: str) -> list:
    """
    يرجّع كل ملفات المشروع كقائمة [{"path": ..., "content": ...}, ...]
    يتجاهل مجلد uploads (الصور) — تلك لها معالجة خاصة في deploy.py
    """
    base = _project_path(user_id, project_name)
    if not os.path.exists(base):
        return []

    files = []
    for root, dirs, filenames in os.walk(base):
        if "uploads" in root.split(os.sep):
            continue
        for filename in filenames:
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, base).replace("\\", "/")
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                files.append({"path": rel_path, "content": content})
            except UnicodeDecodeError:
                # ملف ثنائي (صورة مثلاً) — تجاهله بصمت، له معالجة مختلفة
                continue
            except Exception as e:
                log_warn(f"[FILE_READ_ERR] {full_path} err={e}")
    return files


def get_project_path(user_id: str, project_name: str) -> str:
    """يرجّع المسار الكامل للمشروع — مفيد لو احتجت وصول مباشر."""
    return _project_path(user_id, project_name)


def project_integrity_ok(user_id: str, project_name: str) -> tuple:
    """
    يفحص أن المشروع سليم: الملفات الأساسية موجودة وغير فاضية.
    يرجّع (ok: bool, missing_or_empty: list)
    """
    files = get_project_files(user_id, project_name)
    paths_with_content = {f["path"]: f["content"] for f in files}

    problems = []
    for required in REQUIRED_FILES:
        content = paths_with_content.get(required, "")
        if not content.strip():
            problems.append(required)

    return (len(problems) == 0, problems)


def get_project_size(user_id: str, project_name: str) -> int:
    """يحسب حجم المشروع بالبايت (يشمل الصور)."""
    base = _project_path(user_id, project_name)
    if not os.path.exists(base):
        return 0
    total = 0
    for root, _, filenames in os.walk(base):
        for filename in filenames:
            try:
                total += os.path.getsize(os.path.join(root, filename))
            except OSError:
                pass
    return total


def backup_project(user_id: str, project_name: str) -> str | None:
    """
    ينسخ المشروع احتياطياً قبل الحذف أو التعديل الخطير.
    يحتفظ بآخر نسخة فقط لكل مشروع (لتوفير المساحة).
    """
    src = _project_path(user_id, project_name)
    if not os.path.exists(src):
        return None

    dest = os.path.join(BACKUP_DIR, str(user_id), project_name)
    try:
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        log(f"[BACKUP_OK] user={user_id} project={project_name}")
        return dest
    except Exception as e:
        log_error(f"[BACKUP_FAIL] user={user_id} project={project_name} err={e}")
        return None


def delete_project_files(user_id: str, project_name: str):
    """يحذف ملفات المشروع المحلية مع نسخة احتياطية أولاً (أمان إضافي)."""
    base = _project_path(user_id, project_name)
    if not os.path.exists(base):
        log_warn(f"[DELETE_SKIP] لا يوجد مشروع محلي: user={user_id} project={project_name}")
        return

    backup_project(user_id, project_name)

    try:
        shutil.rmtree(base)
        log(f"[DELETE_OK] user={user_id} project={project_name}")
    except Exception as e:
        log_error(f"[DELETE_ERR] user={user_id} project={project_name} err={e}")


def list_user_projects(user_id: str) -> list:
    """يرجّع أسماء كل المشاريع المحلية لمستخدم معين (مفيد للتشخيص)."""
    base = os.path.join(PROJECTS_DIR, str(user_id))
    if not os.path.exists(base):
        return []
    return [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]

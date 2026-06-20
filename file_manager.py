"""
file_manager.py — إدارة ملفات المشاريع على القرص (طبقة فوق مجلدات projects/<uid>/<name>/).

ميزات:
  - قراءة/حذف ملفات مشروع معيّن لمستخدم معيّن
  - حماية من path traversal (لا يسمح بمسارات تخرج عن مجلد المشروع)
  - عدّ حجم مشاريع المستخدم (يفيد مستقبلاً لحدود استخدام لكل مستخدم)
  - حذف نظيف مع تسجيل الأخطاء بدل تمريرها بصمت
"""
import os
from logger import log

BASE_DIR = os.path.join(os.path.dirname(__file__), "projects")
os.makedirs(BASE_DIR, exist_ok=True)


def _project_dir(user_id: str, project_name: str) -> str:
    return os.path.join(BASE_DIR, str(user_id), project_name)


def _is_safe_path(base: str, target: str) -> bool:
    """يمنع أي مسار يحاول الخروج عن مجلد المشروع (حماية أساسية ضرورية)."""
    base = os.path.abspath(base)
    target = os.path.abspath(target)
    return target == base or target.startswith(base + os.sep)


def get_project_files(user_id: str, project_name: str) -> list:
    """يرجّع كل ملفات المشروع كقائمة {"path": ..., "content": ...} أو [] لو غير موجود."""
    project_dir = _project_dir(user_id, project_name)
    if not os.path.isdir(project_dir):
        return []

    files = []
    for root, _dirs, filenames in os.walk(project_dir):
        for fname in filenames:
            full_path = os.path.join(root, fname)
            if not _is_safe_path(project_dir, full_path):
                continue  # تجاهل أي مسار مشبوه بدل رفع استثناء يكسر التدفق
            rel_path = os.path.relpath(full_path, project_dir)
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                files.append({"path": rel_path.replace(os.sep, "/"), "content": content})
            except (UnicodeDecodeError, OSError) as e:
                # ملفات ثنائية (صور uploads مثلاً) — نتجاهلها هنا، الكود النصي فقط مطلوب
                log(f"[FILE_MANAGER_SKIP] user={user_id} proj={project_name} file={rel_path} err={e}")
    return files


def delete_project_files(user_id: str, project_name: str) -> bool:
    """يحذف مجلد المشروع بالكامل من القرص. يرجع True لو نجح الحذف أو لم يكن المشروع موجوداً أصلاً."""
    project_dir = _project_dir(user_id, project_name)
    if not os.path.isdir(project_dir):
        return True

    try:
        import shutil
        shutil.rmtree(project_dir)
        log(f"[FILE_MANAGER_DELETE_OK] user={user_id} proj={project_name}")
        return True
    except Exception as e:
        log(f"[FILE_MANAGER_DELETE_ERR] user={user_id} proj={project_name} err={e}")
        return False


def get_user_projects_size(user_id: str) -> int:
    """يحسب الحجم الكلي (بايت) لكل مشاريع مستخدم معيّن — يفيد لحدود استخدام مستقبلية."""
    user_dir = os.path.join(BASE_DIR, str(user_id))
    if not os.path.isdir(user_dir):
        return 0

    total = 0
    for root, _dirs, filenames in os.walk(user_dir):
        for fname in filenames:
            full_path = os.path.join(root, fname)
            try:
                total += os.path.getsize(full_path)
            except OSError:
                pass
    return total


def project_files_exist(user_id: str, project_name: str) -> bool:
    """فحص سريع بدون قراءة محتوى أي ملف — يفيد لو احتجنا فقط نعرف هل المشروع موجود محلياً."""
    return os.path.isdir(_project_dir(user_id, project_name))
  

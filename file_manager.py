"""
file_manager.py — إدارة ملفات المشاريع — النسخة المطورة.
"""
import os
import shutil
from logger import log

BASE_DIR = os.path.join(os.path.dirname(__file__), "projects")
os.makedirs(BASE_DIR, exist_ok=True)


def _project_dir(user_id: str, project_name: str) -> str:
    return os.path.join(BASE_DIR, str(user_id), project_name)


def _is_safe(base: str, target: str) -> bool:
    base   = os.path.abspath(base)
    target = os.path.abspath(target)
    return target == base or target.startswith(base + os.sep)


def get_project_files(user_id: str, project_name: str) -> list:
    """يرجع ملفات المشروع النصية كـ [{"path": ..., "content": ...}]."""
    proj_dir = _project_dir(user_id, project_name)
    if not os.path.isdir(proj_dir):
        return []

    files = []
    for root, _, filenames in os.walk(proj_dir):
        for fname in filenames:
            if fname.startswith("."):  # تجاهل .meta وغيرها
                continue
            full = os.path.join(root, fname)
            if not _is_safe(proj_dir, full):
                continue
            rel = os.path.relpath(full, proj_dir).replace(os.sep, "/")
            try:
                with open(full, "r", encoding="utf-8") as f:
                    files.append({"path": rel, "content": f.read()})
            except (UnicodeDecodeError, OSError):
                pass  # ملفات ثنائية (صور) — نتجاهلها
    return files


def delete_project_files(user_id: str, project_name: str) -> bool:
    proj_dir = _project_dir(user_id, project_name)
    if not os.path.isdir(proj_dir):
        return True
    try:
        shutil.rmtree(proj_dir)
        log(f"[FM_DELETE] user={user_id} proj={project_name}")
        return True
    except Exception as e:
        log(f"[FM_DELETE_ERR] user={user_id} proj={project_name} err={e}")
        return False


def get_user_projects_size(user_id: str) -> int:
    user_dir = os.path.join(BASE_DIR, str(user_id))
    if not os.path.isdir(user_dir):
        return 0
    total = 0
    for root, _, files in os.walk(user_dir):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def project_files_exist(user_id: str, project_name: str) -> bool:
    return os.path.isdir(_project_dir(user_id, project_name))

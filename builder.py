"""
builder.py — كتابة ملفات المشروع على القرص — النسخة المطورة.

التحسينات:
  - دعم projectType في البيانات
  - كتابة ذرية (atomic write) لمنع تلف الملفات
  - حماية كاملة من path traversal
  - تسجيل تفصيلي
"""
import os
from logger import log

BASE_DIR = os.path.join(os.path.dirname(__file__), "projects")
os.makedirs(BASE_DIR, exist_ok=True)

REQUIRED_FILES = {"index.html", "style.css", "script.js"}


def _is_safe_path(path: str) -> bool:
    """يرفض أي مسار يحاول الخروج عن مجلد المشروع."""
    if not path or path.startswith("/") or path.startswith("\\"):
        return False
    normalized = os.path.normpath(path)
    return not (normalized.startswith("..") or os.path.isabs(normalized))


def _atomic_write(path: str, content: str) -> None:
    """كتابة ذرية — يضمن عدم ترك ملف نصفه مكتوب."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)


def build_project(data: dict, user_id: str) -> bool:
    """
    يكتب كل ملفات المشروع على القرص.
    يدعم projectType في البيانات.
    يرجع True عند نجاح الكتابة، False عند فشل.
    """
    if not isinstance(data, dict):
        log(f"[BUILDER_ERR] user={user_id} data ليست dict")
        return False

    project_name = data.get("projectName")
    files        = data.get("files", [])
    project_type = data.get("projectType", "website")

    if not project_name or not isinstance(files, list) or not files:
        log(f"[BUILDER_ERR] user={user_id} بيانات ناقصة: name={project_name}")
        return False

    found_paths = {f.get("path") for f in files if isinstance(f, dict)}
    if not REQUIRED_FILES.issubset(found_paths):
        missing = REQUIRED_FILES - found_paths
        log(f"[BUILDER_ERR] user={user_id} proj={project_name} ملفات ناقصة: {missing}")
        return False

    base = os.path.join(BASE_DIR, str(user_id), project_name)
    os.makedirs(base, exist_ok=True)

    # حفظ معلومات المشروع
    meta_path = os.path.join(base, ".meta")
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(f"type={project_type}\nname={project_name}\n")
    except OSError:
        pass

    written = 0
    for f in files:
        rel_path = f.get("path", "")
        content  = f.get("content", "")

        if not _is_safe_path(rel_path):
            log(f"[BUILDER_SKIP] user={user_id} unsafe path={rel_path}")
            continue

        full_path = os.path.join(base, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        try:
            _atomic_write(full_path, content)
            written += 1
        except OSError as e:
            log(f"[BUILDER_WRITE_ERR] user={user_id} path={rel_path} err={e}")

    success = written >= len(REQUIRED_FILES)
    log(f"[BUILDER_{'OK' if success else 'FAIL'}] user={user_id} proj={project_name} "
        f"type={project_type} written={written}/{len(files)}")
    return success

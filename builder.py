"""
builder.py — يكتب ملفات مشروع جديد/معدّل على القرص (projects/<uid>/<projectName>/).

ميزات:
  - فحص بنية data القادمة من AI قبل الكتابة (تجنّب كتابة ملفات فاسدة لو فشل validator سابقاً)
  - حماية من path traversal في أسماء الملفات القادمة من AI (دفاع إضافي حتى لو AI أخطأ)
  - كتابة "atomic" بسيطة: نكتب لملف مؤقت أولاً، وبعد نجاح الكتابة الكاملة نستبدل الملف الأصلي،
    لتجنب ترك ملف نصفه مكتوب لو حدث انقطاع أثناء الكتابة
  - إرجاع True/False بدل الفشل الصامت، عشان bot.py يقدر يتعامل مع الخطأ بوضوح
"""
import os
from logger import log

BASE_DIR = os.path.join(os.path.dirname(__file__), "projects")
os.makedirs(BASE_DIR, exist_ok=True)

REQUIRED_FILES = {"index.html", "style.css", "script.js"}


def _is_safe_relative_path(path: str) -> bool:
    """يرفض أي مسار يحاول الخروج عن مجلد المشروع (../ أو مسار مطلق)."""
    if not path or path.startswith("/") or path.startswith("\\"):
        return False
    normalized = os.path.normpath(path)
    if normalized.startswith("..") or os.path.isabs(normalized):
        return False
    return True


def _atomic_write(path: str, content: str) -> None:
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, path)  # عملية ذرية على أغلب أنظمة الملفات


def build_project(data: dict, user_id: str) -> bool:
    """
    يكتب كل ملفات data["files"] داخل projects/<user_id>/<data['projectName']>/.
    يرجع True عند نجاح كتابة كل الملفات المطلوبة، False لو فيه خلل بالبيانات نفسها.
    """
    if not isinstance(data, dict):
        log(f"[BUILDER_ERR] user={user_id} data ليست dict")
        return False

    project_name = data.get("projectName")
    files = data.get("files", [])

    if not project_name or not isinstance(files, list) or not files:
        log(f"[BUILDER_ERR] user={user_id} بيانات مشروع غير مكتملة: name={project_name} files_count={len(files) if isinstance(files, list) else 'N/A'}")
        return False

    found_paths = {f.get("path") for f in files if isinstance(f, dict)}
    if not REQUIRED_FILES.issubset(found_paths):
        missing = REQUIRED_FILES - found_paths
        log(f"[BUILDER_ERR] user={user_id} proj={project_name} ملفات ناقصة: {missing}")
        return False

    base = os.path.join(BASE_DIR, str(user_id), project_name)
    os.makedirs(base, exist_ok=True)

    written = 0
    for f in files:
        rel_path = f.get("path", "")
        content = f.get("content", "")

        if not _is_safe_relative_path(rel_path):
            log(f"[BUILDER_SKIP_UNSAFE] user={user_id} proj={project_name} path={rel_path}")
            continue

        full_path = os.path.join(base, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        try:
            _atomic_write(full_path, content)
            written += 1
        except OSError as e:
            log(f"[BUILDER_WRITE_ERR] user={user_id} proj={project_name} path={rel_path} err={e}")

    log(f"[BUILDER_OK] user={user_id} proj={project_name} written={written}/{len(files)}")
    return written >= len(REQUIRED_FILES)
  

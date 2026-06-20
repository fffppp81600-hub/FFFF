"""
deploy.py — حفظ المواقع محلياً + استرجاعها (ملفات وصور) من قاعدة البيانات الدائمة.
"""
import os
import shutil
import base64
from logger import log

SITES_DIR = os.path.join(os.path.dirname(__file__), "sites")
os.makedirs(SITES_DIR, exist_ok=True)

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")


def _write_to_disk(name: str, files: list):
    project_dir = os.path.join(SITES_DIR, name)
    os.makedirs(project_dir, exist_ok=True)
    for f in files:
        path = os.path.join(project_dir, f["path"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(f["content"])


def deploy_project(name: str, files: list) -> str:
    if not BASE_URL:
        raise Exception("BASE_URL غير محدد في متغيرات البيئة!")

    _write_to_disk(name, files)
    url = f"{BASE_URL}/s/{name}/"
    log(f"[DEPLOY_LOCAL] project={name} url={url}")
    return url


def delete_vercel_project(name: str):
    project_dir = os.path.join(SITES_DIR, name)
    if os.path.exists(project_dir):
        shutil.rmtree(project_dir)
        log(f"[DELETE_LOCAL] project={name}")


def save_uploaded_image(project_name: str, filename: str, raw_bytes: bytes, mime: str = "image/jpeg"):
    """
    يحفظ الصورة على القرص (للعرض الفوري) + قاعدة البيانات (للديمومة).
    """
    from store import save_image

    uploads_dir = os.path.join(SITES_DIR, project_name, "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    local_path = os.path.join(uploads_dir, filename)
    with open(local_path, "wb") as fp:
        fp.write(raw_bytes)

    b64 = base64.b64encode(raw_bytes).decode("utf-8")
    save_image(project_name, filename, b64, mime)

    log(f"[IMAGE_SAVED] project={project_name} file={filename}")
    return f"{BASE_URL}/s/{project_name}/uploads/{filename}"


def restore_all_sites_from_db():
    """
    يُستدعى عند بدء تشغيل السيرفر:
    1. يعيد كتابة كل ملفات المواقع (html/css/js) من قاعدة البيانات إلى القرص
    2. يعيد كتابة كل الصور المرفوعة من قاعدة البيانات إلى القرص
    لأن Render يمسح القرص بالكامل عند كل إعادة تشغيل.
    """
    from store import get_all_projects, get_all_images

    projects = get_all_projects()
    for p in projects:
        if p["files"]:
            _write_to_disk(p["name"], p["files"])
    log(f"[RESTORE_SITES] استرجاع {len(projects)} مشروع")

    images = get_all_images()
    for img in images:
        uploads_dir = os.path.join(SITES_DIR, img["project_name"], "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        local_path = os.path.join(uploads_dir, img["filename"])
        try:
            raw = base64.b64decode(img["b64_data"])
            with open(local_path, "wb") as fp:
                fp.write(raw)
        except Exception as e:
            log(f"[RESTORE_IMAGE_ERR] {img['filename']} err={e}")
    log(f"[RESTORE_IMAGES] استرجاع {len(images)} صورة")

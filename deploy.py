"""
deploy.py — نشر المواقع محلياً على القرص + استرجاعها من Turso بعد كل إعادة تشغيل.
يشمل أيضاً: حفظ الصور المرفوعة + إزالة الخلفية عبر remove.bg API.
"""
import os
import shutil
import base64
import requests
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


def save_uploaded_image(project_name: str, filename: str, raw_bytes: bytes, mime: str = "image/jpeg") -> str:
    """يحفظ الصورة على القرص + Turso (دائمة)، ويرجع رابطها العام."""
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


def remove_background(raw_bytes: bytes) -> bytes:
    """
    يزيل خلفية صورة عبر remove.bg API ويرجع bytes الصورة الناتجة (PNG شفاف).
    يتطلب متغير بيئة REMOVE_BG_API_KEY.
    لو المفتاح غير موجود أو فشل الطلب، يرجع الصورة الأصلية بدون تعديل (fail-safe).
    """
    api_key = os.getenv("REMOVE_BG_API_KEY", "")

    if not api_key:
        log("[BG_REMOVE_SKIP] REMOVE_BG_API_KEY غير مضبوط — تخطي إزالة الخلفية")
        return raw_bytes

    try:
        response = requests.post(
            "https://api.remove.bg/v1.0/removebg",
            files={"image_file": ("image.jpg", raw_bytes, "image/jpeg")},
            data={"size": "auto"},
            headers={"X-Api-Key": api_key},
            timeout=30,
        )

        if response.status_code == 200:
            log("[BG_REMOVE_OK] remove.bg نجحت")
            return response.content  # PNG شفاف جاهز
        else:
            log(f"[BG_REMOVE_API_ERR] status={response.status_code} body={response.text[:200]}")
            return raw_bytes

    except requests.exceptions.Timeout:
        log("[BG_REMOVE_TIMEOUT] انتهت مهلة remove.bg API")
        return raw_bytes
    except Exception as e:
        log(f"[BG_REMOVE_ERR] {e}")
        return raw_bytes


def restore_all_sites_from_db():
    """
    يُستدعى عند بدء تشغيل السيرفر: يعيد كتابة كل المواقع والصور المحفوظة
    بقاعدة بيانات Turso إلى القرص المحلي (Render يمسح القرص عند كل إعادة تشغيل).
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

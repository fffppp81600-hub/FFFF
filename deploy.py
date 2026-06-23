"""
deploy.py — نشر المواقع على القرص + استرجاعها من Turso — النسخة المطورة.
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
    """يكتب ملفات الموقع على القرص."""
    project_dir = os.path.join(SITES_DIR, name)
    os.makedirs(project_dir, exist_ok=True)
    for f in files:
        path = os.path.join(project_dir, f["path"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as fp:
                fp.write(f["content"])
        except OSError as e:
            log(f"[DEPLOY_WRITE_ERR] name={name} path={f['path']} err={e}")


def deploy_project(name: str, files: list) -> str:
    """ينشر الموقع محلياً ويرجع رابطه."""
    if not BASE_URL:
        raise Exception("BASE_URL غير محدد في متغيرات البيئة!")
    _write_to_disk(name, files)
    url = f"{BASE_URL}/s/{name}/"
    log(f"[DEPLOY_OK] project={name} url={url} files={len(files)}")
    return url


def delete_vercel_project(name: str):
    """يحذف مجلد الموقع من القرص."""
    project_dir = os.path.join(SITES_DIR, name)
    if os.path.exists(project_dir):
        shutil.rmtree(project_dir)
        log(f"[DELETE_OK] project={name}")


def save_uploaded_image(project_name: str, filename: str,
                         raw_bytes: bytes, mime: str = "image/jpeg") -> str:
    """يحفظ صورة على القرص + قاعدة البيانات."""
    from store import save_asset
    import time

    uploads_dir = os.path.join(SITES_DIR, project_name, "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    local_path = os.path.join(uploads_dir, filename)

    with open(local_path, "wb") as fp:
        fp.write(raw_bytes)

    b64  = base64.b64encode(raw_bytes).decode("utf-8")
    url  = f"{BASE_URL}/s/{project_name}/uploads/{filename}" if BASE_URL else ""
    save_asset(project_name, "system", filename, b64, mime, url)

    log(f"[IMAGE_SAVED] project={project_name} file={filename}")
    return url


def remove_background(raw_bytes: bytes) -> bytes:
    """
    يزيل خلفية صورة عبر remove.bg API.
    يرجع الصورة الأصلية عند أي فشل (fail-safe).
    """
    api_key = os.getenv("REMOVE_BG_API_KEY", "")
    if not api_key:
        log("[RMBG_SKIP] REMOVE_BG_API_KEY غير مضبوط")
        return raw_bytes

    try:
        resp = requests.post(
            "https://api.remove.bg/v1.0/removebg",
            files={"image_file": ("image.jpg", raw_bytes, "image/jpeg")},
            data={"size": "auto"},
            headers={"X-Api-Key": api_key},
            timeout=30,
        )
        if resp.status_code == 200:
            log("[RMBG_OK]")
            return resp.content
        log(f"[RMBG_API_ERR] status={resp.status_code} body={resp.text[:200]}")
        return raw_bytes
    except requests.exceptions.Timeout:
        log("[RMBG_TIMEOUT]")
        return raw_bytes
    except Exception as e:
        log(f"[RMBG_ERR] {e}")
        return raw_bytes


def restore_all_sites_from_db():
    """
    يُستدعى عند بدء التشغيل: يعيد كل المواقع + الصور + Assets من Turso للقرص.
    """
    from store import get_all_projects, get_all_images, get_all_assets

    # استرجاع المواقع
    try:
        projects = get_all_projects()
        restored = 0
        for p in projects:
            if p.get("files"):
                _write_to_disk(p["name"], p["files"])
                restored += 1
        log(f"[RESTORE_SITES] تم استرجاع {restored}/{len(projects)} موقع")
    except Exception as e:
        log(f"[RESTORE_SITES_ERR] {e}")

    # استرجاع الصور (الجدول القديم)
    try:
        images = get_all_images()
        for img in images:
            uploads_dir = os.path.join(SITES_DIR, img["project_name"], "uploads")
            os.makedirs(uploads_dir, exist_ok=True)
            local_path = os.path.join(uploads_dir, img["filename"])
            if not os.path.exists(local_path):
                raw = base64.b64decode(img["b64_data"])
                with open(local_path, "wb") as f:
                    f.write(raw)
        log(f"[RESTORE_IMAGES] تم استرجاع {len(images)} صورة")
    except Exception as e:
        log(f"[RESTORE_IMAGES_ERR] {e}")

    # استرجاع Assets الجديدة
    try:
        assets = get_all_assets()
        for asset in assets:
            project_dir = os.path.join(SITES_DIR, asset["project_name"], "uploads")
            os.makedirs(project_dir, exist_ok=True)
            local_path = os.path.join(project_dir, asset["filename"])
            if not os.path.exists(local_path):
                raw = base64.b64decode(asset["b64_data"])
                with open(local_path, "wb") as f:
                    f.write(raw)
        log(f"[RESTORE_ASSETS] تم استرجاع {len(assets)} asset")
    except Exception as e:
        log(f"[RESTORE_ASSETS_ERR] {e}")

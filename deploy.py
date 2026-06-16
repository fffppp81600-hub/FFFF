import os
import shutil
from logger import log

SITES_DIR = os.path.join(os.path.dirname(__file__), "sites")
os.makedirs(SITES_DIR, exist_ok=True)

# لازم يكون https — حطه في Render Environment Variables
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")


def deploy_project(name: str, files: list) -> str:
    if not BASE_URL:
        raise Exception("BASE_URL غير محدد في متغيرات البيئة!")

    project_dir = os.path.join(SITES_DIR, name)
    os.makedirs(project_dir, exist_ok=True)

    for f in files:
        path = os.path.join(project_dir, f["path"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(f["content"])

    url = f"{BASE_URL}/s/{name}/"
    log(f"[DEPLOY_LOCAL] project={name} url={url}")
    return url


def delete_vercel_project(name: str):
    project_dir = os.path.join(SITES_DIR, name)
    if os.path.exists(project_dir):
        shutil.rmtree(project_dir)
        log(f"[DELETE_LOCAL] project={name}")

import os
import requests
import base64
from logger import log

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
USERNAME = os.getenv("GITHUB_USERNAME", "")

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}


def create_repo(repo_name: str) -> bool:
    url = "https://api.github.com/user/repos"
    data = {
        "name": repo_name,
        "private": False,
        "auto_init": False
    }
    try:
        r = requests.post(url, json=data, headers=HEADERS, timeout=30)
        log(f"[GITHUB_CREATE] repo={repo_name} status={r.status_code}")
        return r.status_code == 201
    except Exception as e:
        log(f"[GITHUB_CREATE_ERROR] {e}")
        return False


def upload_files(repo_name: str, files: list) -> bool:
    """رفع ملفات إلى GitHub repo"""
    success = True

    for file in files:
        path = file.get("path", "")
        content = file.get("content", "")

        if not path or not content:
            continue

        b64 = base64.b64encode(content.encode()).decode()
        url = f"https://api.github.com/repos/{USERNAME}/{repo_name}/contents/{path}"

        # التحقق من وجود الملف (للحصول على sha إذا موجود)
        sha = None
        try:
            check = requests.get(url, headers=HEADERS, timeout=15)
            if check.status_code == 200:
                sha = check.json().get("sha")
        except Exception:
            pass

        data = {
            "message": f"Update {path}",
            "content": b64
        }
        if sha:
            data["sha"] = sha

        try:
            r = requests.put(url, json=data, headers=HEADERS, timeout=30)
            if r.status_code not in (200, 201):
                log(f"[GITHUB_UPLOAD_FAIL] path={path} status={r.status_code}")
                success = False
        except Exception as e:
            log(f"[GITHUB_UPLOAD_ERROR] path={path} error={e}")
            success = False

    return success

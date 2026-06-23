"""
github.py — رفع المشاريع لـ GitHub — النسخة المطورة.
"""
import os
import base64
import requests
from logger import log

GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN", "")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept":        "application/vnd.github.v3+json",
}


def _is_configured() -> bool:
    return bool(GITHUB_TOKEN and GITHUB_USERNAME)


def create_repo(repo_name: str, private: bool = False) -> bool:
    if not _is_configured():
        log("[GITHUB_SKIP] توكن أو اسم مستخدم غير مضبوط")
        return False
    try:
        r = requests.post(
            "https://api.github.com/user/repos",
            json={"name": repo_name, "private": private, "auto_init": False},
            headers=HEADERS,
            timeout=30,
        )
        ok = r.status_code == 201
        log(f"[GITHUB_CREATE] repo={repo_name} status={r.status_code} ok={ok}")
        return ok
    except Exception as e:
        log(f"[GITHUB_CREATE_ERR] {e}")
        return False


def upload_files(repo_name: str, files: list) -> bool:
    if not _is_configured():
        return False
    success = True
    for f in files:
        path    = f.get("path", "")
        content = f.get("content", "")
        if not path or not content:
            continue
        b64 = base64.b64encode(content.encode()).decode()
        url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/contents/{path}"

        # SHA للتحديث إذا الملف موجود
        sha = None
        try:
            check = requests.get(url, headers=HEADERS, timeout=15)
            if check.status_code == 200:
                sha = check.json().get("sha")
        except Exception:
            pass

        body = {"message": f"Update {path}", "content": b64}
        if sha:
            body["sha"] = sha

        try:
            r = requests.put(url, json=body, headers=HEADERS, timeout=30)
            if r.status_code not in (200, 201):
                log(f"[GITHUB_UPLOAD_FAIL] path={path} status={r.status_code}")
                success = False
        except Exception as e:
            log(f"[GITHUB_UPLOAD_ERR] path={path} err={e}")
            success = False

    return success


def deploy_to_github_pages(repo_name: str, files: list) -> str:
    """يرفع المشروع ويرجع رابط GitHub Pages."""
    if not _is_configured():
        return ""
    create_repo(repo_name)
    if upload_files(repo_name, files):
        # تفعيل GitHub Pages
        try:
            requests.post(
                f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/pages",
                json={"source": {"branch": "main", "path": "/"}},
                headers=HEADERS,
                timeout=15,
            )
        except Exception:
            pass
        return f"https://{GITHUB_USERNAME}.github.io/{repo_name}/"
    return ""

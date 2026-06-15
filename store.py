import json
import os
import time
from threading import Lock

STORE_FILE = "data/projects.json"
_lock = Lock()


def _load() -> dict:
    """تحميل البيانات من الملف"""
    if not os.path.exists(STORE_FILE):
        os.makedirs(os.path.dirname(STORE_FILE), exist_ok=True)
        return {}

    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save(data: dict):
    """حفظ البيانات إلى الملف"""
    os.makedirs(os.path.dirname(STORE_FILE), exist_ok=True)
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_project(user_id: str, name: str, url: str):
    with _lock:
        data = _load()
        data.setdefault(user_id, [])

        # حذف المشروع القديم بنفس الاسم إذا موجود
        data[user_id] = [p for p in data[user_id] if p["name"] != name]

        data[user_id].append({
            "name": name,
            "url": url,
            "created_at": int(time.time())
        })

        _save(data)


def get_projects(user_id: str) -> list:
    with _lock:
        data = _load()
        return data.get(user_id, [])


def get_project(user_id: str, name: str) -> dict | None:
    with _lock:
        data = _load()
        for p in data.get(user_id, []):
            if p["name"] == name:
                return p
        return None


def update_project(user_id: str, name: str, url: str):
    with _lock:
        data = _load()

        if user_id not in data:
            return

        for p in data[user_id]:
            if p["name"] == name:
                p["url"] = url
                p["updated_at"] = int(time.time())
                break

        _save(data)


# 🔥 هذا هو الدالة الناقصة اللي كانت تسبب المشكلة
def delete_project(user_id: str, name: str):
    with _lock:
        data = _load()

        if user_id not in data:
            return

        data[user_id] = [p for p in data[user_id] if p["name"] != name]

        _save(data)

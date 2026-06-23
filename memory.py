"""
memory.py — نظام ذاكرة متكامل للمشاريع والمحادثات.

ميزات:
  - ذاكرة RAM سريعة للجلسة الحالية
  - مزامنة تلقائية مع قاعدة Turso (دائمة بين التشغيلات)
  - تتذكر: آخر مشروع، كامل تاريخ المحادثة، نوع المشروع، التعديلات
  - حد أقصى 20 رسالة في الذاكرة لتجنب تجاوز حد الـ prompt
"""
from typing import Optional
from logger import log

# ─── RAM Cache ───────────────────────────────
_projects:     dict = {}   # uid -> آخر بيانات مشروع
_conversations: dict = {}  # uid -> [{"role": ..., "content": ...}]
_edit_context: dict = {}   # proj_name -> {"summary": str, "last_edit": str}


# ══════════════════════════════════════════════
# آخر مشروع
# ══════════════════════════════════════════════
def set_last(user_id: str, project: dict):
    """يحفظ آخر مشروع في RAM + قاعدة البيانات."""
    _projects[user_id] = project
    _sync_to_db(user_id)


def get_last(user_id: str) -> Optional[dict]:
    """يرجع آخر مشروع — يبحث في RAM أولاً ثم قاعدة البيانات."""
    if user_id in _projects:
        return _projects[user_id]
    return _load_from_db(user_id)


def clear(user_id: str):
    """يمسح ذاكرة مستخدم معين."""
    _projects.pop(user_id, None)
    _conversations.pop(user_id, None)
    try:
        from store import clear_session
        clear_session(user_id)
    except Exception as e:
        log(f"[MEM_CLEAR_ERR] uid={user_id} err={e}")


# ══════════════════════════════════════════════
# تاريخ المحادثة
# ══════════════════════════════════════════════
def add_message(user_id: str, role: str, content: str):
    """يضيف رسالة لتاريخ محادثة المستخدم."""
    hist = _conversations.setdefault(user_id, [])
    hist.append({"role": role, "content": content})
    # نحافظ على آخر 20 رسالة فقط
    if len(hist) > 20:
        _conversations[user_id] = hist[-20:]
    _sync_history_to_db(user_id)


def get_history(user_id: str) -> list:
    """يرجع تاريخ المحادثة — RAM أولاً ثم DB."""
    if user_id in _conversations:
        return _conversations[user_id]
    try:
        from store import get_session
        session = get_session(user_id)
        hist = session.get("history", [])
        if hist:
            _conversations[user_id] = hist
        return hist
    except Exception:
        return []


def set_history(user_id: str, history: list):
    """يضبط تاريخ المحادثة كاملاً (للاستخدام من bot.py)."""
    _conversations[user_id] = history[-20:]
    _sync_history_to_db(user_id)


def clear_history(user_id: str):
    """يمسح تاريخ المحادثة."""
    _conversations.pop(user_id, None)
    try:
        from store import clear_session
        clear_session(user_id)
    except Exception:
        pass


# ══════════════════════════════════════════════
# سياق التعديل
# ══════════════════════════════════════════════
def set_edit_context(proj_name: str, summary: str, last_edit: str = ""):
    """يحفظ ملخص وآخر تعديل لمشروع معين — يُستخدم لتوجيه AI في التعديلات."""
    _edit_context[proj_name] = {"summary": summary, "last_edit": last_edit}


def get_edit_context(proj_name: str) -> dict:
    return _edit_context.get(proj_name, {"summary": "", "last_edit": ""})


def update_edit_context(proj_name: str, edit_request: str):
    """يضيف آخر تعديل لسياق المشروع."""
    ctx = _edit_context.setdefault(proj_name, {"summary": "", "last_edit": ""})
    ctx["last_edit"] = edit_request[:200]


# ══════════════════════════════════════════════
# مزامنة مع قاعدة البيانات
# ══════════════════════════════════════════════
def _sync_to_db(user_id: str):
    try:
        from store import save_session
        hist = _conversations.get(user_id, [])
        proj = _projects.get(user_id, {})
        proj_name = proj.get("projectName", "") if proj else ""
        save_session(user_id, hist, proj_name)
    except Exception as e:
        log(f"[MEM_SYNC_ERR] uid={user_id} err={e}")


def _sync_history_to_db(user_id: str):
    try:
        from store import save_session
        hist = _conversations.get(user_id, [])
        proj = _projects.get(user_id, {})
        proj_name = proj.get("projectName", "") if proj else ""
        save_session(user_id, hist, proj_name)
    except Exception as e:
        log(f"[MEM_HIST_SYNC_ERR] uid={user_id} err={e}")


def _load_from_db(user_id: str) -> Optional[dict]:
    try:
        from store import get_session, get_project_files_db
        session = get_session(user_id)
        proj_name = session.get("current_proj", "")
        if not proj_name:
            return None
        files = get_project_files_db(user_id, proj_name)
        if files:
            data = {"projectName": proj_name, "files": files}
            _projects[user_id] = data
            return data
    except Exception as e:
        log(f"[MEM_LOAD_ERR] uid={user_id} err={e}")
    return None


# ══════════════════════════════════════════════
# نظرة عامة على الذاكرة (للـ debugging)
# ══════════════════════════════════════════════
def memory_stats() -> dict:
    return {
        "cached_projects":     len(_projects),
        "cached_conversations": len(_conversations),
        "edit_contexts":       len(_edit_context),
    }

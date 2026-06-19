"""
logger.py — نظام تسجيل متقدم.
يدعم: مستويات (INFO/WARN/ERROR/SUCCESS)، حفظ بملف يومي، طباعة ملونة، وقص الرسائل الطويلة.
"""
import os
import sys
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# ألوان ANSI للطرفية (تظهر بشكل صحيح في Render logs أيضاً)
_COLORS = {
    "INFO":    "\033[94m",   # أزرق
    "SUCCESS": "\033[92m",   # أخضر
    "WARN":    "\033[93m",   # أصفر
    "ERROR":   "\033[91m",   # أحمر
    "RESET":   "\033[0m",
}

_MAX_LINE_LEN = 2000  # حماية من رسائل ضخمة تطغى على اللوق


def _today_log_path() -> str:
    date_str = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(LOG_DIR, f"{date_str}.log")


def _write(level: str, message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    safe_message = str(message)
    if len(safe_message) > _MAX_LINE_LEN:
        safe_message = safe_message[:_MAX_LINE_LEN] + " ...[TRUNCATED]"

    line = f"[{timestamp}] [{level}] {safe_message}"

    # طباعة بالطرفية (مع ألوان لو مدعومة)
    color = _COLORS.get(level, "")
    reset = _COLORS["RESET"]
    print(f"{color}{line}{reset}", flush=True)

    # حفظ بملف (best-effort — لا نكسر التطبيق لو فشلت الكتابة)
    try:
        with open(_today_log_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def log(message: str):
    """التوافق مع الاستخدام القديم — مستوى INFO افتراضي."""
    _write("INFO", message)


def log_success(message: str):
    _write("SUCCESS", message)


def log_warn(message: str):
    _write("WARN", message)


def log_error(message: str):
    _write("ERROR", message)


def get_recent_logs(lines: int = 50) -> str:
    """يرجّع آخر N سطر من لوق اليوم — مفيد للتشخيص السريع عبر أمر بوت لو احتجت."""
    path = _today_log_path()
    if not os.path.exists(path):
        return "لا يوجد سجل لليوم بعد."
    try:
        with open(path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        return "".join(all_lines[-lines:])
    except Exception as e:
        return f"خطأ بقراءة السجل: {e}"

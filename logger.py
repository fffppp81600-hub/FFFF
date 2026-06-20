"""
logger.py — نظام تسجيل (logging) متقدم.

ميزات:
  - مستويات تسجيل (INFO, WARN, ERROR, DEBUG) بدل دالة log() واحدة بلا تصنيف
  - طباعة فورية لـ stdout (يلتقطها Render في الـ logs) + كتابة لملف محلي للرجوع له لاحقاً
  - تدوير تلقائي للملف عند تجاوز حجم معيّن (تجنب امتلاء القرص المحدود في Render)
  - حماية كاملة: أي خطأ داخل اللوغر نفسه لا يكسر تنفيذ البوت (best-effort logging)
"""
import os
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "bot.log")

MAX_LOG_BYTES = 2 * 1024 * 1024  # 2MB


def _rotate_if_needed():
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_BYTES:
            backup = LOG_FILE + ".old"
            if os.path.exists(backup):
                os.remove(backup)
            os.rename(LOG_FILE, backup)
    except Exception:
        pass


def _write(level: str, message: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {message}"

    try:
        print(line, flush=True)
    except Exception:
        pass

    try:
        _rotate_if_needed()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def log(message: str):
    """التوقيع القديم — يبقى للتوافق مع كل استدعاءات log() الموجودة بالكود."""
    _write("INFO", message)


def log_info(message: str):
    _write("INFO", message)


def log_warn(message: str):
    _write("WARN", message)


def log_error(message: str):
    _write("ERROR", message)


def log_debug(message: str):
    if os.getenv("DEBUG", "").lower() in ("1", "true", "yes"):
        _write("DEBUG", message)
      

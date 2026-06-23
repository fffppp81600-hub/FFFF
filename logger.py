"""
logger.py — نظام تسجيل متقدم — النسخة المطورة.
مستويات: INFO, WARN, ERROR, DEBUG.
تدوير تلقائي للملف عند 2MB.
"""
import os
from datetime import datetime

LOG_DIR  = os.path.join(os.path.dirname(__file__), "logs")
LOG_FILE = os.path.join(LOG_DIR, "bot.log")
MAX_BYTES = 2 * 1024 * 1024  # 2MB

os.makedirs(LOG_DIR, exist_ok=True)


def _rotate():
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_BYTES:
            backup = LOG_FILE + ".old"
            if os.path.exists(backup):
                os.remove(backup)
            os.rename(LOG_FILE, backup)
    except Exception:
        pass


def _write(level: str, message: str):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {message}"
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        _rotate()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def log(message: str):       _write("INFO",  message)
def log_info(message: str):  _write("INFO",  message)
def log_warn(message: str):  _write("WARN",  message)
def log_error(message: str): _write("ERROR", message)


def log_debug(message: str):
    if os.getenv("DEBUG", "").lower() in ("1", "true", "yes"):
        _write("DEBUG", message)

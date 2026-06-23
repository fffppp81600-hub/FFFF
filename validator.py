"""
validator.py — تحقق من مخرجات AI — النسخة المطورة.
يدعم projectType الجديد ويتحقق من جودة كود الألعاب.
"""
import json
import re
from logger import log

REQUIRED_FILES  = {"index.html", "style.css", "script.js"}
MIN_CONTENT_LEN = 30
GAME_SCRIPT_MIN = 300  # الألعاب تحتاج كود JS أطول


def _extract_braces(text: str) -> str:
    start = text.find("{")
    if start == -1:
        raise ValueError("لا يوجد { في النص")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if esc:   esc = False; continue
        if c == "\\" and in_str: esc = True; continue
        if c == '"': in_str = not in_str; continue
        if in_str: continue
        if c == "{":   depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    end = text.rfind("}")
    if end > start:
        return text[start:end + 1]
    raise ValueError("لا يوجد } مطابق")


def _fix_trailing_commas(text: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _check_structure(data: dict) -> str | None:
    if not isinstance(data, dict):
        return "الناتج ليس dict"
    if "projectName" not in data:
        return "حقل projectName غير موجود"
    if "files" not in data or not isinstance(data["files"], list):
        return "حقل files غير موجود أو ليس list"

    paths   = {f.get("path") for f in data["files"] if isinstance(f, dict)}
    missing = REQUIRED_FILES - paths
    if missing:
        return f"ملفات ناقصة: {missing}"

    is_game = data.get("projectType") == "game"

    for f in data["files"]:
        if not isinstance(f, dict):
            continue
        content = f.get("content", "")
        path    = f.get("path", "")
        if not isinstance(content, str):
            return f"محتوى غير نصي في {path}"
        min_len = GAME_SCRIPT_MIN if (is_game and path == "script.js") else MIN_CONTENT_LEN
        if len(content.strip()) < min_len:
            return f"محتوى قصير جداً في {path} ({len(content.strip())} < {min_len})"

    return None


def safe_parse(text: str) -> dict | None:
    if not text or not text.strip():
        log("[VALIDATOR_FAIL] النص فارغ")
        return None

    raw = text.strip()
    raw = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r"```$", "", raw).strip()

    try:
        extracted = _extract_braces(raw)
    except ValueError as e:
        log(f"[VALIDATOR_FAIL] استخراج JSON فشل: {e}")
        return None

    try:
        data = json.loads(extracted)
    except json.JSONDecodeError:
        try:
            data = json.loads(_fix_trailing_commas(extracted))
        except json.JSONDecodeError as e:
            log(f"[VALIDATOR_FAIL] JSON غير صالح: {e}")
            return None

    error = _check_structure(data)
    if error:
        log(f"[VALIDATOR_FAIL] بنية خاطئة: {error}")
        return None

    return data

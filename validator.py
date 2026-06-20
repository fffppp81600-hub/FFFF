"""
validator.py — يحوّل النص الخام القادم من ai.py إلى dict موثوق، أو يرجع None مع تسجيل السبب.

ميزات:
  - استخراج JSON حتى لو فيه نص زائد قبله/بعده أو ``` ماركداون
  - إصلاح أخطاء شائعة (فواصل زائدة قبل } أو ]) قبل الاستسلام
  - فحص بنية أعمق من json.loads البسيط: يتحقق من الملفات الثلاثة المطلوبة وأن محتواها غير فارغ
  - تسجيل واضح لسبب الفشل في logger بدل فشل صامت يصعّب تتبع الأعطال
"""
import json
import re
from logger import log

REQUIRED_FILES = {"index.html", "style.css", "script.js"}
MIN_CONTENT_LEN = 30  # أي ملف أقصر من هذا يعتبر فاسد/ناقص


def _extract_braces(text: str) -> str:
    """يستخرج أول كتلة {...} متوازنة، يتجاهل أي نص زائد قبلها أو بعدها."""
    start = text.find("{")
    if start == -1:
        raise ValueError("لا يوجد { في النص")

    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if esc:
            esc = False
            continue
        if c == "\\" and in_str:
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
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
    """يرجع رسالة الخطأ لو فيه مشكلة، أو None لو البنية سليمة."""
    if not isinstance(data, dict):
        return "الناتج ليس dict"
    if "projectName" not in data:
        return "حقل projectName غير موجود"
    if "files" not in data or not isinstance(data["files"], list):
        return "حقل files غير موجود أو ليس list"

    paths = {f.get("path") for f in data["files"] if isinstance(f, dict)}
    missing = REQUIRED_FILES - paths
    if missing:
        return f"ملفات ناقصة: {missing}"

    for f in data["files"]:
        if not isinstance(f, dict):
            continue
        content = f.get("content", "")
        if not isinstance(content, str) or len(content.strip()) < MIN_CONTENT_LEN:
            return f"محتوى قصير جداً أو فارغ في {f.get('path')}"

    return None


def safe_parse(text: str) -> dict | None:
    """
    نقطة الدخول الرئيسية: يحاول تحويل النص الخام إلى dict صالح للاستخدام مباشرة.
    يرجع None فقط بعد تسجيل سبب واضح للفشل في logger.
    """
    if not text or not text.strip():
        log("[VALIDATOR_FAIL] النص الخام فارغ")
        return None

    raw = text.strip()
    raw = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()

    try:
        extracted = _extract_braces(raw)
    except ValueError as e:
        log(f"[VALIDATOR_FAIL] استخراج JSON فشل: {e} | raw[:150]={raw[:150]}")
        return None

    try:
        data = json.loads(extracted)
    except json.JSONDecodeError:
        try:
            fixed = _fix_trailing_commas(extracted)
            data = json.loads(fixed)
        except json.JSONDecodeError as e:
            log(f"[VALIDATOR_FAIL] JSON غير صالح حتى بعد الإصلاح: {e} | extracted[:150]={extracted[:150]}")
            return None

    error = _check_structure(data)
    if error:
        log(f"[VALIDATOR_FAIL] بنية غير صحيحة: {error}")
        return None

    return data
  

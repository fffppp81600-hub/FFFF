"""
ai.py — Gemini 2.0 Flash with forced JSON output mode.
response_mime_type="application/json" forces Gemini to return valid JSON always.
"""
import os
import re
import json
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

BASE_SYSTEM = """You are an elite Senior Frontend Engineer and UI/UX Designer AI.

REQUIRED JSON FORMAT (return exactly this structure):
{
  "projectName": "kebab-case-name-max-30-chars",
  "files": [
    {"path": "index.html", "content": "COMPLETE HTML"},
    {"path": "style.css",  "content": "COMPLETE CSS"},
    {"path": "script.js",  "content": "COMPLETE JS"}
  ]
}

TECH RULES:
- Pure vanilla HTML5 + CSS3 + ES6 JS only. No frameworks, no npm, no imports.
- Tailwind v4 CDN in index.html: <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
- index.html must have: <link rel="stylesheet" href="style.css"> and <script src="script.js"></script>
- Dark premium UI: glassmorphism, gradients, smooth animations.
- Arabic request → dir="rtl" lang="ar" on <html>, Cairo font from Google Fonts.
- Games/apps → 100% working logic. No stubs. No TODOs. Everything functional.
- Implement EVERY feature the user mentions. Nothing skipped."""

BUILD_PROMPT = """Build a complete production-ready web app. Implement every feature fully.

Request: {request}"""

EDIT_PROMPT = """Update this web project. Apply every requested change. Keep untouched features intact.

Current code:
{current_code}

Changes to apply:
{edit_request}"""

# JSON config يجبر Gemini يرجع JSON نظيف دائماً
JSON_CONFIG = types.GenerateContentConfig(
    response_mime_type="application/json",
    temperature=0.7,
)


def _validate(data: dict) -> None:
    if not isinstance(data, dict):
        raise ValueError("Not a dict")
    if "projectName" not in data or "files" not in data:
        raise ValueError(f"Missing keys: {list(data.keys())}")
    paths = {f.get("path") for f in data.get("files", [])}
    missing = {"index.html", "style.css", "script.js"} - paths
    if missing:
        raise ValueError(f"Missing files: {missing}")
    for f in data["files"]:
        if not f.get("content", "").strip():
            raise ValueError(f"Empty content: {f.get('path')}")


def _call(prompt: str, retries: int = 4) -> str:
    last_err = last_raw = None
    full_prompt = BASE_SYSTEM + "\n\n" + prompt

    for i in range(1, retries + 1):
        try:
            r = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=full_prompt,
                config=JSON_CONFIG,
            )
            last_raw = r.text.strip()

            # مع response_mime_type=json الرد دايماً JSON مباشرة
            # لكن نتأكد على كل حال
            text = last_raw
            # أزل أي ```json ``` لو وُجدت
            text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
            text = re.sub(r"```$", "", text).strip()

            data = json.loads(text)
            _validate(data)
            return text

        except json.JSONDecodeError as e:
            last_err = f"JSON parse error attempt {i}: {e}"
        except ValueError as e:
            last_err = f"Validation error attempt {i}: {e}"
        except Exception as e:
            last_err = f"API error attempt {i}: {e}"

        if i < retries:
            time.sleep(2 * i)

    raise RuntimeError(f"Gemini failed after {retries} attempts. Last: {last_err} | raw[:200]={(last_raw or '')[:200]}")


def builder(request: str) -> str:
    return _call(BUILD_PROMPT.format(request=request))


def editor(edit_request: str, current_code: str = "") -> str:
    return _call(EDIT_PROMPT.format(
        current_code=current_code or "(no source files — treat as new project)",
        edit_request=edit_request,
    ))


# Legacy aliases
def planner(text: str) -> str: return builder(text)
def coder(plan: str) -> str:   return plan
def reviewer(code: str) -> str: return code

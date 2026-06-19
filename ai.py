"""
ai.py — Groq (Llama 3.3 70B) — مجاني، سريع، كوتة عالية جداً.
يحتاج: pip install groq
ومتغير بيئة: GROQ_API_KEY (مجاني من https://console.groq.com)
"""
import os
import re
import json
import time
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "llama-3.3-70b-versatile"

BASE_SYSTEM = """You are an elite Senior Frontend Engineer, Game Developer, and UI/UX Designer AI with 15 years of experience building award-winning web applications.

OUTPUT CONTRACT — NEVER VIOLATE:
Return ONLY a raw JSON object. No markdown. No backticks. No explanation. No text before or after.
First char = {   Last char = }

JSON STRUCTURE:
{
  "projectName": "kebab-case-max-30-chars",
  "files": [
    {"path": "index.html", "content": "...FULL COMPLETE HTML..."},
    {"path": "style.css",  "content": "...FULL COMPLETE CSS..."},
    {"path": "script.js",  "content": "...FULL COMPLETE JS..."}
  ]
}

TECHNOLOGY RULES:
- Pure vanilla HTML5 + CSS3 + ES6 JS ONLY
- NO React, NO Vue, NO npm, NO imports, NO require()
- Tailwind v4 via CDN ALWAYS in index.html head:
  <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
- index.html MUST have:
  <link rel="stylesheet" href="style.css">
  <script src="script.js"></script> before </body>

DESIGN REQUIREMENTS — MANDATORY:
- Create STUNNING, PREMIUM, PRODUCTION-READY interfaces
- Use: multi-stop mesh gradients, glassmorphism (backdrop-blur-xl), neon glow effects
- Smooth CSS animations and transitions on everything
- Hover states, active states, focus states on all interactive elements
- Professional typography with Google Fonts
- Fully responsive (mobile-first)
- Dark theme by default unless user specifies otherwise
- NO plain/boring/basic designs — every element must look premium

ARABIC LANGUAGE RULE:
- If request is in Arabic OR targets Arabic users:
  * <html lang="ar" dir="rtl">
  * Google Font: Cairo or Tajawal
  * Full RTL layout

CONTENT & FEATURES RULES — CRITICAL:
- READ the user request CAREFULLY
- Implement EVERY feature mentioned — nothing skipped, nothing stubbed
- Add REALISTIC placeholder content (real product names, real prices, real descriptions)
- For stores: add real-looking products with images from picsum.photos
- For games: 100% working gameplay, scoring, win/lose conditions
- For dashboards: real charts using Chart.js from CDN, real-looking data
- Write AT LEAST 200 lines of HTML, 100 lines of CSS, 150 lines of JS
- The result must look like a REAL website a professional company would use

FORBIDDEN:
- Empty or placeholder content like "Product 1", "Lorem ipsum", "TODO"
- Basic unstyled pages
- Missing features the user asked for
- Stub functions with no implementation"""

BUILD_PROMPT = """Build a complete, stunning, production-ready website for this request.

USER REQUEST: {request}

REQUIREMENTS:
1. Implement EVERY feature the user mentioned with full working logic
2. Add realistic content — real product names, descriptions, prices if it's a store
3. Make it look PREMIUM and PROFESSIONAL — not a basic template
4. Arabic request = RTL + Cairo font + Arabic content throughout
5. Minimum: 200 lines HTML, 100 lines CSS, 150 lines JS

Return ONLY the JSON object."""

EDIT_PROMPT = """Update this existing web project with the requested changes.

CURRENT CODE:
{current_code}

CHANGES REQUESTED: {edit_request}

RULES:
- Apply EVERY requested change completely
- Keep ALL existing features that weren't mentioned for removal
- Maintain the same design quality and style
- Return ALL 3 files complete even if only one changed

Return ONLY the JSON object."""


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
        if len(f.get("content", "").strip()) < 50:
            raise ValueError(f"Content too short in {f.get('path')}")


def _extract_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    if start == -1:
        raise ValueError("No { found")
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
                return text[start:i+1]
    end = text.rfind("}")
    if end > start:
        return text[start:end+1]
    raise ValueError("No matching }")


def _fix_json(text: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _call(prompt: str, retries: int = 5) -> str:
    last_err = last_raw = None
    messages = [
        {"role": "system", "content": BASE_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    for i in range(1, retries + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.8,
                max_tokens=8000,
                response_format={"type": "json_object"},
            )
            last_raw = resp.choices[0].message.content.strip()
            extracted = _extract_json(last_raw)

            try:
                data = json.loads(extracted)
            except json.JSONDecodeError:
                extracted = _fix_json(extracted)
                data = json.loads(extracted)

            _validate(data)
            return extracted

        except json.JSONDecodeError as e:
            last_err = f"JSON error attempt {i}: {e}"
        except ValueError as e:
            last_err = f"Validation error attempt {i}: {e}"
        except Exception as e:
            last_err = f"API error attempt {i}: {e}"

        if i < retries:
            time.sleep(2 * i)

    raise RuntimeError(f"Groq failed {retries}x. Last: {last_err} | raw[:300]={(last_raw or '')[:300]}")


def builder(request: str) -> str:
    return _call(BUILD_PROMPT.format(request=request))


def editor(edit_request: str, current_code: str = "") -> str:
    return _call(EDIT_PROMPT.format(
        current_code=current_code or "(no source — treat as new project)",
        edit_request=edit_request,
    ))


def planner(text: str) -> str: return builder(text)
def coder(plan: str) -> str:   return plan
def reviewer(code: str) -> str: return code

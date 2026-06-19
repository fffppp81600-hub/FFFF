"""
ai.py — Groq (Llama 3.3 70B) — محرك بناء وتعديل مواقع بفهم عميق للسياق.

ميزات الفهم العميق:
  - استنتاج الميزات الضمنية غير المذكورة صراحة (متجر = سلة + دفع حتى لو ما ذكرها المستخدم)
  - تلخيص الكود الحالي تلقائياً قبل التعديل (orientation سريع لـ AI)
  - تصنيف نوع طلب التعديل (تصميم / إضافة ميزة / حذف / تصحيح خطأ / محتوى)
  - فحوصات جودة تلقائية متعددة حسب نوع الموقع
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


BASE_SYSTEM = """You are an elite Senior Frontend Engineer, Game Developer, and UI/UX Designer AI with 15 years of experience. You think deeply before coding: you infer the user's true intent, including features they implied but didn't explicitly state.

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

DEEP UNDERSTANDING RULES — THINK LIKE A PRODUCT OWNER:
- "Store/متجر" implies: working cart, category navigation, product images, prices, checkout flow — even if not all listed explicitly
- "Game/لعبة" implies: score tracking, win/lose states, restart button, fair difficulty
- "Dashboard/لوحة تحكم" implies: charts, summary stat cards, sidebar/nav, realistic numbers
- Vague wording ("خله احلى" / "make it nicer") means: improve visual polish only (gradients, spacing, animations, typography), never change structure or remove features
- "غير اللون" without specifying an element means: apply to the primary brand color (buttons, headers, accents) consistently across all files
- Always reconcile new requests with everything already built — never silently delete a feature the user didn't ask to remove

DESIGN REQUIREMENTS — MANDATORY:
- STUNNING, PREMIUM, PRODUCTION-READY interfaces
- Multi-stop mesh gradients, glassmorphism (backdrop-blur-xl), neon glow effects
- Smooth CSS animations and transitions on everything
- Hover/active/focus states on all interactive elements
- Professional typography with Google Fonts, fully responsive (mobile-first)
- Dark theme by default unless user specifies otherwise
- NO plain/boring/basic designs

ARABIC LANGUAGE RULE:
- Arabic request or Arabic audience: <html lang="ar" dir="rtl">, Google Font Cairo/Tajawal, full RTL layout

CONTENT & FEATURES RULES — CRITICAL:
- Implement EVERY feature mentioned OR implied — nothing skipped, nothing stubbed
- Realistic content (real product names, real prices, real descriptions)
- Stores: product photos from https://picsum.photos/seed/SEEDNAME/400/500 (unique seed per product)
- Games: 100% working gameplay, scoring, win/lose conditions
- Dashboards: real Chart.js charts from CDN, realistic data
- Minimum 200 lines HTML, 100 lines CSS, 250+ lines JS for stores/apps

E-COMMERCE — MANDATORY WORKING LOGIC (most common failure point, be extremely careful):
- ALL products in one JS array of objects: {id, name, category, price, image}
- Every category button calls ONE shared filter function over the SAME array and re-renders — never separate disconnected HTML sections per category
- Real cart state (`let cart = []`): Add-to-cart pushes + calls updateCartUI() + updateCartCount()
- Cart icon fixed top-left (Salla-style) with live badge count; click opens panel with items, qty, remove, subtotal, and "إتمام الشراء" button
- Checkout: address input ("موقعك"), order summary, payment options including black rounded "Apple Pay" button (visual simulation only: sliding sheet, spinner, success check — never claim real payment)
- Every step (browse → filter → cart → checkout → pay → confirm) must work with zero dead buttons

FORBIDDEN:
- Placeholder content like "Product 1", "Lorem ipsum", "TODO"
- Basic unstyled pages, missing implied features, stub functions
- Category buttons that don't filter correctly
- Add-to-cart buttons with no visible state change
- Claiming real payment processing happens"""


BUILD_PROMPT = """Build a complete, stunning, production-ready website for this request.

USER REQUEST: {request}

Before coding, think about what this type of site implicitly needs beyond what's literally written, and include it.

REQUIREMENTS:
1. Implement EVERY feature mentioned or reasonably implied, with full working logic
2. Realistic content — real product names, descriptions, prices if it's a store
3. PREMIUM and PROFESSIONAL look — not a basic template
4. Arabic request = RTL + Cairo font + Arabic content throughout
5. Stores: category filters must filter live, cart must track items visibly, checkout must work with simulated Apple Pay
6. Minimum: 200 lines HTML, 100 lines CSS, 250+ lines JS for stores

Return ONLY the JSON object."""


EDIT_PROMPT = """You are modifying an existing live website. Understand the current code deeply before changing anything.

CODE SUMMARY (quick orientation): {code_summary}

CURRENT FULL CODE:
{current_code}

USER'S EDIT REQUEST: {edit_request}

INSTRUCTIONS:
1. Identify the change type: (a) visual/style only, (b) new feature, (c) removal, (d) bug fix, (e) content change
2. If vague ("خله احلى", "زيد شي", "غيره"), infer the most sensible interpretation from what the site currently does — improve without breaking structure
3. Apply the change completely across ALL files that need it (a color change may need both CSS and inline Tailwind classes updated)
4. NEVER remove or break an existing working feature unless explicitly asked
5. Return ALL 3 files complete, even unchanged ones

Return ONLY the JSON object."""


def summarize_code(current_code: str) -> str:
    """تلخيص سريع للكود الحالي بدون استدعاء AI إضافي — orientation للنموذج."""
    if not current_code or len(current_code.strip()) < 20:
        return "لا يوجد كود سابق — مشروع جديد بالكامل."

    lower = current_code.lower()
    features = []
    checks = [
        (["cart", "سلة"], "نظام سلة تسوق"),
        (["category", "قسم", "filter"], "فلترة/أقسام منتجات"),
        (["apple pay", "checkout", "دفع"], "صفحة دفع/checkout"),
        (["score", "game"], "منطق لعبة (نقاط/فوز/خسارة)"),
        (["chart", "canvas"], "رسوم بيانية / dashboard"),
        (["cairo", 'dir="rtl"'], "موقع عربي بتخطيط RTL"),
        (["picsum", "placeholder.com"], "صور منتجات placeholder"),
    ]
    for keywords, label in checks:
        if any(k in lower for k in keywords):
            features.append(label)

    files_found = re.findall(r"--- (\S+) ---", current_code)
    files_note = f"الملفات الموجودة: {', '.join(set(files_found))}" if files_found else ""

    if features:
        return f"{files_note}\nالميزات المكتشفة حالياً: {', '.join(features)}."
    return f"{files_note}\nموقع بسيط بدون ميزات تفاعلية معقدة مكتشفة."


def classify_edit_intent(edit_request: str) -> str:
    """تصنيف سريع لنوع طلب التعديل — يساعد القرار لو الطلب غامض."""
    vague_markers = ["احلى", "افضل", "حسن", "طور", "زيد شي", "ضيف شي", "غيره شوي"]
    if any(m in edit_request for m in vague_markers) and len(edit_request.split()) < 5:
        return "vague_polish"
    if any(w in edit_request for w in ["حذف", "شيل", "ازل", "remove", "delete"]):
        return "removal"
    if any(w in edit_request for w in ["لون", "تصميم", "شكل", "خط", "style", "color"]):
        return "style_only"
    if any(w in edit_request for w in ["لا يعمل", "ما يعمل", "خطأ", "مشكلة", "bug", "fix"]):
        return "bug_fix"
    return "feature_or_content"


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


def _looks_like_store(text: str) -> bool:
    keywords = ["متجر", "محل", "منتج", "سلة", "تسوق", "store", "shop", "cart", "product"]
    return any(k in text for k in keywords)


def _has_cart_logic(js: str) -> bool:
    markers = ["cart", "addToCart", "Cart", "السلة"]
    hits = sum(1 for m in markers if m in js)
    return hits >= 2 and len(js) > 800


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
                return text[start:i + 1]
    end = text.rfind("}")
    if end > start:
        return text[start:end + 1]
    raise ValueError("No matching }")


def _fix_json(text: str) -> str:
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _call(prompt: str, retries: int = 5, check_store: bool = False) -> str:
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
                temperature=0.7,
                max_tokens=16000,
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

            if check_store:
                js_content = next((f["content"] for f in data["files"] if f["path"] == "script.js"), "")
                if not _has_cart_logic(js_content):
                    raise ValueError("متجر بدون منطق سلة حقيقي في script.js — إعادة المحاولة")

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
    return _call(
        BUILD_PROMPT.format(request=request),
        check_store=_looks_like_store(request),
    )


def editor(edit_request: str, current_code: str = "") -> str:
    summary = summarize_code(current_code)
    intent = classify_edit_intent(edit_request)

    intent_hints = {
        "vague_polish": "النية المكتشفة: طلب تحسين بصري عام فقط. لا تغيّر البنية أو تحذف ميزات — فقط حسّن المظهر.",
        "removal": "النية المكتشفة: طلب حذف/إزالة شيء معين. تأكد من حذفه بدقة دون التأثير على باقي الميزات.",
        "style_only": "النية المكتشفة: تعديل تصميم/ألوان/خطوط. لا تغيّر المنطق الوظيفي.",
        "bug_fix": "النية المكتشفة: تصحيح خطأ أو مشكلة. ركّز على إيجاد سبب العطل في الكود الحالي وإصلاحه دون كسر أي شيء آخر يعمل.",
        "feature_or_content": "النية المكتشفة: إضافة ميزة جديدة أو محتوى. أضفها بالتكامل الكامل مع الكود الموجود.",
    }
    enriched_request = f"{edit_request}\n\n[{intent_hints.get(intent, '')}]"

    return _call(
        EDIT_PROMPT.format(
            current_code=current_code or "(no source — treat as new project)",
            code_summary=summary,
            edit_request=enriched_request,
        ),
        check_store=_looks_like_store(current_code + edit_request),
    )


def planner(text: str) -> str: return builder(text)
def coder(plan: str) -> str:   return plan
def reviewer(code: str) -> str: return code

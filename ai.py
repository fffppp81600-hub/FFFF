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
- For stores: add real-looking products with real photo URLs from https://picsum.photos/seed/SEEDNAME/400/500 (use a unique seed per product so each photo differs, e.g. picsum.photos/seed/tshirt1/400/500)
- For games: 100% working gameplay, scoring, win/lose conditions
- For dashboards: real charts using Chart.js from CDN, real-looking data
- Write AT LEAST 200 lines of HTML, 100 lines of CSS, 300 lines of JS for e-commerce sites
- The result must look like a REAL website a professional company would use

E-COMMERCE SITES — MANDATORY WORKING LOGIC (read carefully, this is the #1 failure point):
- Store ALL products in a single JS array of objects: {id, name, category, price, image}
- Category filtering: each category button/tab MUST have a data-category attribute or onclick that calls a function like showCategory('tshirts') which:
  1. Loops through ALL product cards
  2. Shows only cards whose category matches, hides all others (display:none / display:block, or filter the array and re-render)
  3. NEVER hardcode separate static HTML sections per category that don't connect to the filter buttons — the buttons MUST control visibility of ALL products, every category must work identically
- Shopping cart MUST be real working state:
  1. Maintain a JS array `cart = []` (or use a global object) in script.js
  2. "Add to cart" button onclick MUST push the product into `cart` and call `updateCartUI()` and `updateCartCount()`
  3. A cart icon fixed top-left (like Salla-style) shows a badge with item count, updates live on every add
  4. Clicking the cart icon opens a cart panel/modal/sidebar showing all added products with quantity, price, remove button, and subtotal
  5. Cart panel MUST have a "إتمام الشراء" / "Checkout" button that navigates to or reveals the checkout section
- Checkout flow MUST work end-to-end:
  1. Checkout section/page has an input field for delivery address/location ("موقعك")
  2. Checkout shows order summary (items from cart, total price)
  3. Checkout offers payment method selection: at minimum an "Apple Pay" styled button (black, rounded, with the Apple logo using a unicode  character or inline SVG, official Apple Pay look) and a "بطاقة ائتمان" option
  4. Clicking the Apple Pay button shows a realistic Apple Pay UI simulation (sheet/modal sliding up, dark background, "Pay with Apple Pay" text, then a fake processing spinner, then a success checkmark screen) — this is a VISUAL SIMULATION for demo purposes only, never claim real payment processing in the UI text, but make the simulation look polished and convincing
  5. After "payment", show a clear order confirmation screen/message
  6. Every step (cart → checkout → payment → confirmation) must be reachable by clicking through the UI with NO dead buttons and NO console errors
- TEST YOUR OWN LOGIC MENTALLY: every category tab must show different filtered products, every add-to-cart must visibly increment the cart badge, every cart item must be removable, checkout must always be reachable from the cart

FORBIDDEN:
- Empty or placeholder content like "Product 1", "Lorem ipsum", "TODO"
- Basic unstyled pages
- Missing features the user asked for
- Stub functions with no implementation
- Category buttons that don't filter correctly (this is the most common bug — avoid it)
- Add-to-cart buttons that don't update any visible cart state
- Claiming real payment processing happens (always keep Apple Pay as a visual-only simulation)"""

BUILD_PROMPT = """Build a complete, stunning, production-ready website for this request.

USER REQUEST: {request}

REQUIREMENTS:
1. Implement EVERY feature the user mentioned with full working logic
2. Add realistic content — real product names, descriptions, prices if it's a store
3. Make it look PREMIUM and PROFESSIONAL — not a basic template
4. Arabic request = RTL + Cairo font + Arabic content throughout
5. If this is a store/e-commerce site: category filters MUST actually filter products live, cart MUST actually track added items with a visible counter, and checkout MUST be reachable from the cart with a working (simulated) payment flow including Apple Pay visual style
6. Minimum: 200 lines HTML, 100 lines CSS, 250+ lines JS for stores

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

            # فحص جودة إضافي للمتاجر — تأكد إن منطق السلة/الفلترة موجود فعلياً
            if _looks_like_store(prompt):
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


def _looks_like_store(prompt: str) -> bool:
    keywords = ["متجر", "محل", "منتج", "سلة", "تسوق", "store", "shop", "cart", "product"]
    return any(k in prompt for k in keywords)


def _has_cart_logic(js: str) -> bool:
    """تحقق سريع إن فيه مصفوفة سلة ودوال تحديثها — مو فقط زر بلا منطق."""
    markers = ["cart", "addToCart", "Cart", "السلة"]
    hits = sum(1 for m in markers if m in js)
    return hits >= 2 and len(js) > 800


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

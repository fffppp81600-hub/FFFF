"""
ai.py — Groq (Llama 3.3 70B) — محرك بناء وتعديل مواقع بفهم عميق للسياق.

التحسينات في هذا الإصدار:
  ① البوت أذكى: PLANNING_SYSTEM محسّن — يسأل أسئلة أعمق، يفهم نوع الموقع، يقترح أفكار ذكية
  ② AI أفضل: BASE_SYSTEM محسّن — تعليمات تصميم أغنى، أنيميشن احترافية، UX أعلى مستوى
  ③ جودة المواقع: تفاصيل بصرية متقدمة، micro-interactions، خطوط وألوان متناسقة
"""
import os
import re
import json
import time
from typing import Optional
from dotenv import load_dotenv
from groq import Groq
import httpx
import web_search

load_dotenv()

MODEL = "llama-3.3-70b-versatile"

# ─────────────────────────────────────────────
# نظام تناوب المفاتيح (Key Rotation)
# يدعم من مفتاح واحد إلى 10 مفاتيح. يضاف بـ .env كالتالي:
#   GROQ_API_KEY=key1
#   GROQ_API_KEY_2=key2  ...  GROQ_API_KEY_10=key10
# ─────────────────────────────────────────────
_API_KEYS = []
_first_key = os.getenv("GROQ_API_KEY")
if _first_key and _first_key.strip():
    _API_KEYS.append(_first_key.strip())
for _i in range(2, 11):
    _k = os.getenv(f"GROQ_API_KEY_{_i}")
    if _k and _k.strip():
        _API_KEYS.append(_k.strip())

if not _API_KEYS:
    raise RuntimeError("لا يوجد أي GROQ_API_KEY في متغيرات البيئة!")

_clients = [
    Groq(
        api_key=k,
        timeout=60.0,
        http_client=httpx.Client(http2=False),
    )
    for k in _API_KEYS
]
_current_key_index = 0


def _get_client():
    return _clients[_current_key_index]


def _rotate_key() -> bool:
    global _current_key_index
    _current_key_index = (_current_key_index + 1) % len(_clients)
    return _current_key_index != 0


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(s in msg for s in ["429", "rate_limit", "quota", "tokens per minute", "request too large"])


# ═══════════════════════════════════════════════════════════════════
# ① BASE_SYSTEM — محسّن لجودة كود وتصميم أعلى
# ═══════════════════════════════════════════════════════════════════
BASE_SYSTEM = """You are a world-class Senior Frontend Engineer, Creative Director, and UI/UX Specialist AI.
You don't just build websites — you craft digital experiences. Before writing a single line, you deeply analyze
the user's true intent, their audience, and the emotional tone the site should convey.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT CONTRACT — NEVER VIOLATE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Return ONLY a raw JSON object. No markdown. No backticks. No explanation. No preamble.
First char = {   Last char = }

JSON STRUCTURE:
{"projectName": "kebab-case-max-30-chars", "files": [{"path": "index.html", "content": "..."}, {"path": "style.css", "content": "..."}, {"path": "script.js", "content": "..."}]}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TECHNOLOGY STACK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Pure vanilla HTML5 + CSS3 + ES6 JS ONLY. NO React/Vue/npm/build tools.
- Tailwind v4 CDN: <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
- index.html must link style.css (<link rel="stylesheet" href="style.css">) and script.js (<script src="script.js" defer></script>).
- Google Fonts via CDN only. Default Arabic: Cairo + Tajawal. Default Latin: Inter + Poppins.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCOPE RULE — MOST IMPORTANT, NEVER VIOLATE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Build EXACTLY what the user asked for — nothing more, nothing less.
- Simple page request (logo + name + background + animation) = build ONLY that. Zero e-commerce elements.
- A brand name does NOT imply a store. Only add cart/products/checkout if words like
  "متجر / منتجات / بيع / سلة / store / shop / cart / products" actually appear.
- The E-COMMERCE section below applies ONLY when a store was explicitly requested.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
② DEEP PRODUCT THINKING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Think like a product owner AND a creative director simultaneously:
- "متجر/Store" → working cart, category nav, product grid, prices, checkout flow, empty-state messages
- "لعبة/Game" → score counter, win/lose screen, restart, sound feedback (Web Audio API if fitting)
- "داشبورد/Dashboard" → animated stat cards, Chart.js via CDN charts, sidebar with active states
- "بورتفوليو/Portfolio" → smooth scroll, project cards with hover reveal, skills progress bars, contact form
- "مطعم/Restaurant" → menu sections, item cards with images, reservation form, opening hours
- "صفحة هبوط/Landing" → hero with CTA, features grid, testimonials, FAQ accordion, footer
- Vague polish request ("خله احلى") → upgrade visuals only, never touch logic or structure
- Color-only request → apply consistently to all brand touchpoints, never touch JS logic

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
③ PREMIUM DESIGN SYSTEM (apply to EVERY project)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COLORS & GRADIENTS:
- Default: rich dark theme. Background: #0a0a0f or #0d0d1a. Cards: rgba(255,255,255,0.04).
- Primary accent: choose one bold color that fits the brand (electric blue #6366f1, emerald #10b981,
  amber #f59e0b, rose #f43f5e, violet #8b5cf6). Never use generic grey.
- Gradients: always multi-stop. Example: linear-gradient(135deg, #667eea 0%, #764ba2 100%).
- Glassmorphism cards: background: rgba(255,255,255,0.05); backdrop-filter: blur(20px);
  border: 1px solid rgba(255,255,255,0.1); box-shadow: 0 8px 32px rgba(0,0,0,0.3).

TYPOGRAPHY:
- Headings: bold/black weight (700-900), tight letter-spacing for impact.
- Body: 400-500 weight, comfortable line-height (1.6-1.8).
- Never mix more than 2 font families.
- Arabic text: always font-family Cairo or Tajawal, dir="rtl", text-align: right.

ANIMATIONS & MICRO-INTERACTIONS (mandatory, not optional):
- Page load: elements fade-in + slide-up with staggered delays (0.1s apart).
  Use IntersectionObserver for scroll-triggered animations — never animate everything on load.
- Buttons: scale(1.05) on hover + box-shadow glow effect matching brand color.
- Cards: translateY(-8px) + enhanced shadow on hover, transition 0.3s ease.
- Links/nav items: underline slide-in animation on hover.
- Loading states: skeleton screens or pulse animation — never blank white.
- Scroll progress bar at top of page (thin colored line).
- Smooth scroll behavior: html { scroll-behavior: smooth; }

LAYOUT:
- Always fully responsive: mobile-first, breakpoints at 640px / 768px / 1024px / 1280px.
- Use CSS Grid for complex layouts, Flexbox for alignment.
- Generous whitespace: padding/margin should feel spacious, never cramped.
- Max content width: 1200px centered with auto margins.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
E-COMMERCE MANDATORY LOGIC (ONLY if store explicitly requested)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- ALL products in one JS array: {id, name, category, price, image, description, rating}
- Category filter buttons operate on the SAME array via one shared renderProducts() function
- Cart state: let cart = []; persisted to localStorage
- Cart icon (fixed top corner) shows live badge count, opens slide-in panel
- Cart panel: item list with quantities, remove button, subtotal, checkout CTA
- Checkout: name + address form, order summary, simulated payment button (never claim real payment)
- Search bar filters products in real-time as user types
- Product cards: image, name, price, rating stars, "أضف للسلة" button — all functional
- Empty cart state: friendly message with shopping icon
- Every single button must work — zero dead UI

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTENT & ASSETS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Product images: https://picsum.photos/seed/UNIQUESEED/400/500 (different seed per product)
- Hero backgrounds: https://picsum.photos/seed/HEROSEED/1600/900
- Icons: use Unicode emoji or simple CSS shapes — never leave icon placeholders
- Real Arabic content: never use Lorem ipsum. Use realistic Arabic names, descriptions, prices.
- Prices in SAR (ريال) for Arabic sites.

REAL LINKS RULE: If "روابط حقيقية" section exists in request, use those URLs EXACTLY.
YouTube watch?v=ID → embed/ID in <iframe>. Other links → <a href="..."> with provided title.

SCRIPT.JS: Even static pages need script.js with at least: scroll progress bar + IntersectionObserver
fade-in + one micro-interaction. Never leave it truly empty.

FORBIDDEN: Lorem ipsum, "Product 1" placeholders, stub functions, broken filters,
fake payment claims, adding store elements when none were requested, empty script.js."""


# ═══════════════════════════════════════════════════════════════════
# BUILD PROMPT — محسّن
# ═══════════════════════════════════════════════════════════════════
BUILD_PROMPT = """Build a complete, production-ready, visually stunning website.

REQUEST: {request}

CRITICAL SCOPE RULE:
- Build ONLY what was explicitly requested — nothing more.
- No store/cart/products unless the request clearly asks for them.
- If a product category was mentioned (e.g. electronics), ALL products must be from that category only.

QUALITY CHECKLIST (every item must be ✓ before returning):
✓ Premium dark design with rich gradients and glassmorphism cards
✓ Scroll-triggered fade-in animations via IntersectionObserver
✓ Button hover effects (scale + glow)
✓ Card hover effects (lift + shadow)
✓ Fully responsive (mobile → desktop)
✓ Realistic Arabic content (no Lorem ipsum, no "Product 1")
✓ script.js has scroll progress bar + animations at minimum
✓ All interactive elements actually work

Return ONLY the JSON object. No explanation."""


# ═══════════════════════════════════════════════════════════════════
# EDIT PROMPT — محسّن
# ═══════════════════════════════════════════════════════════════════
EDIT_PROMPT = """You are editing an existing website. Read and fully understand the current code before making ANY change.

CURRENT SITE SUMMARY: {code_summary}

CURRENT CODE:
{current_code}

EDIT REQUEST: {edit_request}

EDITING RULES:
1. Apply the requested change precisely — never touch unrelated parts.
2. Never silently remove a working feature unless explicitly asked.
3. If adding a visual element, match the existing design language exactly.
4. If fixing a bug, fix only that bug — don't refactor the whole file.
5. Return ALL 3 files complete and correct, even if only one file changed.
6. Preserve all existing animations and interactions unless asked to change them.

Return ONLY the JSON object."""


# ─────────────────────────────────────────────
# Code compression
# ─────────────────────────────────────────────
def compress_code_for_prompt(current_code: str, max_chars: int = 7000) -> str:
    if not current_code:
        return current_code
    compressed = re.sub(r"[ \t]{2,}", " ", current_code)
    compressed = re.sub(r"\n{3,}", "\n\n", compressed)
    if len(compressed) <= max_chars:
        return compressed
    return compressed[:max_chars] + "\n\n[...الباقي مقتطع. حافظ على كل ما لم يظهر كما هو.]"


def summarize_code(current_code: str) -> str:
    if not current_code or len(current_code.strip()) < 20:
        return "لا يوجد كود سابق — مشروع جديد."
    lower = current_code.lower()
    features = []
    checks = [
        (["cart", "سلة", "addtocart"],           "سلة تسوق"),
        (["category", "قسم", "filter"],           "فلترة/أقسام"),
        (["apple pay", "checkout", "دفع"],        "صفحة دفع"),
        (["score", "game", "لعبة"],               "منطق لعبة"),
        (["chart", "canvas", "recharts"],         "رسوم بيانية"),
        (["cairo", 'dir="rtl"', "tajawal"],       "موقع عربي RTL"),
        (["intersectionobserver", "scroll"],      "أنيميشن تمرير"),
        (["localstorage", "sessionstorage"],      "تخزين محلي"),
        (["fetch(", "xmlhttprequest", "axios"],   "طلبات API"),
        (["modal", "popup", "dialog"],            "نوافذ منبثقة"),
    ]
    for keywords, label in checks:
        if any(k in lower for k in keywords):
            features.append(label)

    # استخراج عنوان الصفحة
    title_match = re.search(r"<title>(.*?)</title>", current_code, re.IGNORECASE)
    title_info = f" | عنوان: {title_match.group(1)}" if title_match else ""

    return (f"الميزات: {', '.join(features)}{title_info}." if features
            else f"موقع بسيط{title_info}.")


def classify_edit_intent(edit_request: str) -> str:
    vague_markers = ["احلى", "افضل", "حسن", "طور", "زيد شي", "ضيف شي", "جمّل", "حسّن"]
    if any(m in edit_request for m in vague_markers) and len(edit_request.split()) < 6:
        return "vague_polish"
    if any(w in edit_request for w in ["حذف", "شيل", "ازل", "امسح", "remove", "delete"]):
        return "removal"
    if any(w in edit_request for w in ["لون", "تصميم", "شكل", "خط", "خلفية", "style", "color", "font", "background"]):
        return "style_only"
    if any(w in edit_request for w in ["لا يعمل", "ما يعمل", "خطأ", "مشكلة", "مكسور", "bug", "fix", "error"]):
        return "bug_fix"
    if any(w in edit_request for w in ["عنوان", "title", "اسم الموقع", "اسم الصفحة"]):
        return "title_change"
    return "feature_or_content"


def extract_dominant_color(image_path: str) -> Optional[str]:
    try:
        from PIL import Image
        img = Image.open(image_path).convert("RGB").resize((50, 50))
        pixels = list(img.getdata())
        n = len(pixels)
        r = sum(p[0] for p in pixels) // n
        g = sum(p[1] for p in pixels) // n
        b = sum(p[2] for p in pixels) // n
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return None


def _build_image_instruction(image_url: Optional[str], image_path: Optional[str]) -> str:
    if not image_url:
        return ""
    dominant = extract_dominant_color(image_path) if image_path else None
    block = f"\n\n[صورة مرفقة: {image_url}]"
    if dominant:
        block += f" [اللون السائد: {dominant} — استخدمه كلون أساسي للموقع]"
    block += (
        " إذا كانت لوقو: ضعها كـ <img src='{url}'> في الهيدر بارتفاع 60-80px مع padding مناسب. "
        "إذا كانت صورة منتج: غيّر image لذلك المنتج فقط في مصفوفة script.js. "
        "إذا كانت خلفية أو ديكور: ضعها كـ background-image في الـ hero section."
    ).replace("{url}", image_url)
    return block


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
        content = f.get("content", "")
        path = f.get("path", "")
        if path == "script.js" and content.strip() == "":
            continue
        if len(content.strip()) < 10:
            raise ValueError(f"Content empty in {path} (len={len(content.strip())})")


def _looks_like_store(text: str) -> bool:
    keywords = ["متجر", "منتجات", "منتج", "سلة التسوق", "سلة المشتريات", "بيع المنتجات",
                "store", "shop", "cart", "products", "e-commerce", "ecommerce"]
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
    depth, in_str, esc = 0, False, False
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
        {"role": "user",   "content": prompt},
    ]

    for i in range(1, retries + 1):
        try:
            client = _get_client()
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.45,
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

            if check_store:
                js_content = next(
                    (f["content"] for f in data["files"] if f["path"] == "script.js"), ""
                )
                if not _has_cart_logic(js_content):
                    raise ValueError("متجر بدون منطق سلة — إعادة المحاولة")

            return extracted

        except json.JSONDecodeError as e:
            last_err = f"JSON error attempt {i}: {e}"
        except ValueError as e:
            last_err = f"Validation error attempt {i}: {e}"
        except Exception as e:
            cause = getattr(e, "__cause__", None)
            cause_info = f" | cause={type(cause).__name__}: {cause}" if cause else ""
            last_err = f"API error attempt {i}: {type(e).__name__}: {e}{cause_info}"
            if _is_quota_error(e) and len(_clients) > 1:
                _rotate_key()

        if i < retries:
            time.sleep(3 * i)

    raise RuntimeError(
        f"Groq failed {retries}x across {len(_clients)} key(s). Last: {last_err} | raw={last_raw}"
    )


# ═══════════════════════════════════════════════════════════════════
# ① PLANNING_SYSTEM — محسّن: أذكى + أعمق + يقترح + يفهم نوع الموقع
# ═══════════════════════════════════════════════════════════════════
PLANNING_SYSTEM = """أنت مستشار مواقع ذكي وودود، خبير في UX وبناء المنتجات الرقمية.
مهمتك في هذه المرحلة: تفهم بعمق ما يريده المستخدم وتساعده يوضح فكرته قبل البناء.

كيف تتصرف:
1. حلل نوع الموقع المطلوب: هل هو متجر؟ لعبة؟ بورتفوليو؟ صفحة هبوط؟ داشبورد؟ مطعم؟ غيره؟
2. بناءً على النوع، اسأل عن التفاصيل المهمة الناقصة فقط (لا تسأل عن شيء واضح بالفعل):
   - متجر → نوع المنتجات؟ عدد الأقسام؟ هل يبغى سلة كاملة؟
   - لعبة → نوع اللعبة؟ مستوى الصعوبة؟ للموبايل أو الكمبيوتر؟
   - بورتفوليو → مجاله؟ أبرز مشاريعه؟ هل يبغى نموذج تواصل؟
   - صفحة هبوط → المنتج/الخدمة؟ الجمهور المستهدف؟ هل فيه CTA؟
   - مطعم → نوع الأكل؟ هل يبغى قائمة طعام؟ حجز طاولات؟
3. اقترح فكرة أو ميزة ذكية واحدة بناءً على فهمك (لكن وضّح إنها اقتراح مو إلزامي).
4. لا تكتب أي كود أبداً — فقط محادثة نصية طبيعية وذكية.
5. ردودك مختصرة ومباشرة (3-5 جمل) — لا تطول بدون سبب.

قرار الجاهزية:
- حلّل آخر رسالة: هل فيها نية واضحة للبدء؟ (يلا / ابدأ / سويها / تمام / جاهز / ماشي / انشر / اعملها)
- لو نعم → ابدأ ردك بـ "[READY]" ثم جملة تأكيد قصيرة بما ستبنيه.
- لو لا → ابدأ ردك بـ "[CONTINUE]" ثم ردك الطبيعي.

[READY] أو [CONTINUE] إلزامي في أول كلمة دائماً بدون استثناء."""


def plan_chat(conversation: list) -> tuple[str, bool]:
    """
    محادثة تخطيط ذكية — تحلل السياق الكامل وتقرر هل المستخدم جاهز للبناء.
    يرجع (نص الرد, جاهز_للبناء: bool).
    """
    messages = [{"role": "system", "content": PLANNING_SYSTEM}] + conversation

    last_err = None
    for i in range(1, 4):
        try:
            client = _get_client()
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.55,
                max_tokens=350,
            )
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("[READY]"):
                return raw.replace("[READY]", "", 1).strip(), True
            if raw.startswith("[CONTINUE]"):
                return raw.replace("[CONTINUE]", "", 1).strip(), False
            return raw, False
        except Exception as e:
            last_err = e
            if _is_quota_error(e) and len(_clients) > 1:
                _rotate_key()
            time.sleep(2 * i)

    raise RuntimeError(f"Groq planning chat failed: {last_err}")


def needs_real_links(conversation_text: str) -> Optional[str]:
    triggers = [
        "فيديو", "فيديوهات", "يوتيوب", "youtube", "رابط حقيقي", "روابط حقيقية",
        "منافس", "منافسين", "مواقع تشبه", "أمثلة حقيقية", "حط لي روابط",
        "اعطني روابط", "اعطيني روابط", "افضل", "best", "top",
    ]
    if any(t in conversation_text for t in triggers):
        return conversation_text[-200:]
    return None


def build_from_conversation(conversation: list) -> str:
    """
    يبني الموقع من كامل محادثة التخطيط — يضمن الالتزام بكل ما ذكره المستخدم.
    """
    user_only = [m["content"] for m in conversation if m["role"] == "user"]
    full_request = "\n".join(user_only)

    # لو المحادثة طويلة جداً، نحتفظ بالفكرة الأساسية + آخر 3 توضيحات
    if len(user_only) > 5:
        trimmed = [user_only[0]] + user_only[-3:]
        full_request = "\n".join(trimmed)

    links_block = ""
    if web_search.is_search_available():
        search_query = needs_real_links(full_request)
        if search_query:
            results = web_search.search_real_links(search_query, max_results=5)
            links_block = web_search.format_links_for_prompt(results)

    scope_reminder = (
        "\n\nقاعدة الالتزام الصارمة: ابنِ حرفياً ما طلبه المستخدم أعلاه فقط — لا زيادة ولا نقصان. "
        "إذا لم يذكر صراحة متجر/منتجات/سلة/أقسام → لا تضف أياً منها أبداً. "
        "إذا ذكر نوع منتجات معين → كل محتوى الموقع من هذا النوع فقط."
    )

    prompt = BUILD_PROMPT.format(request=full_request) + scope_reminder + links_block
    return _call(prompt, check_store=_looks_like_store(full_request))


def builder(request: str) -> str:
    return _call(BUILD_PROMPT.format(request=request), check_store=_looks_like_store(request))


def editor(
    edit_request: str,
    current_code: str = "",
    image_url: Optional[str] = None,
    image_path: Optional[str] = None,
) -> str:
    summary  = summarize_code(current_code)
    intent   = classify_edit_intent(edit_request)
    compressed = compress_code_for_prompt(current_code)

    intent_hints = {
        "vague_polish":      "[نية: تحسين بصري فقط — لا تغيّر البنية أو المنطق]",
        "removal":           "[نية: حذف دقيق — لا تؤثر على الميزات الأخرى]",
        "style_only":        "[نية: تصميم/ألوان فقط — لا تلمس JS أبداً]",
        "bug_fix":           "[نية: إصلاح خطأ محدد — لا تعيد هيكلة الكود]",
        "title_change":      "[نية: تغيير عنوان الصفحة <title> فقط في index.html]",
        "feature_or_content":"[نية: إضافة ميزة/محتوى كامل ومتكامل]",
    }

    image_instruction = _build_image_instruction(image_url, image_path)
    enriched = f"{edit_request} {intent_hints.get(intent, '')}{image_instruction}"

    return _call(
        EDIT_PROMPT.format(
            current_code=compressed or "(لا يوجد كود — مشروع جديد)",
            code_summary=summary,
            edit_request=enriched,
        ),
        check_store=_looks_like_store(current_code + edit_request),
    )


def planner(text: str) -> str:  return builder(text)
def coder(plan: str) -> str:    return plan
def reviewer(code: str) -> str: return code

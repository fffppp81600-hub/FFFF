"""
ai.py — Groq (Llama 3.3 70B) — محرك بناء وتعديل مواقع بفهم عميق للسياق.

الميزات الفعلية الحالية:
  - محادثة تخطيط قبل البناء (plan_chat): يرد على المستخدم ويسأل عن تفاصيل ناقصة،
    ولا يعتبر الطلب جاهزاً للبناء إلا لما يكتشف فعلياً نية تأكيد واضحة بالسياق
  - بناء من كامل المحادثة (build_from_conversation): يلتزم حرفياً بكل ما ذكره المستخدم
    عبر كل رسائله، ويُمنع صريحاً من اختراع أقسام/منتجات/ميزات لم تُذكر
  - استنتاج الميزات الضمنية المنطقية فقط لما يُذكر (متجر = سلة + دفع تلقائياً)، بدون
    تخمين تفاصيل محتوى لم يُصرَّح بها
  - تلخيص الكود الحالي تلقائياً قبل التعديل + ضغطه لتقليل استهلاك التوكنات
  - تصنيف نوع طلب التعديل (تصميم / إضافة ميزة / حذف / تصحيح خطأ / محتوى)
  - دعم صورة مرفقة من المستخدم: رابط مباشر + استخراج لونها السائد محلياً (Pillow)
  - نظام تناوب مفاتيح Groq (حتى 10 مفاتيح) — يتحول تلقائياً عند تجاوز حد التوكنات
  - max_tokens وحجم prompt مضبوطين ليبقوا تحت حد Groq المجاني (12000 توكن/دقيقة)
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
#   GROQ_API_KEY_2=key2
#   GROQ_API_KEY_3=key3
#   ... إلى GROQ_API_KEY_10
# عند فشل مفتاح (حد التوكنات/الكوتة)، ينتقل تلقائياً للمفتاح التالي بدون أي تدخل،
# والسياق (الكود الحالي للمشروع) محفوظ بقاعدة البيانات لا بالمفتاح، فلا حاجة لإعادة شرح الفكرة.
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
_current_key_index = 0  # يبدأ من أول مفتاح، يتقدّم عند فشل المفتاح الحالي


def _get_client():
    return _clients[_current_key_index]


def _rotate_key() -> bool:
    """
    يتقدّم للمفتاح التالي. يرجع True لو فيه مفتاح آخر لم نجربه بهذه الدورة، False لو رجعنا لأول مفتاح
    (يعني جربنا كل المفاتيح المتاحة ولا واحد منها نجح).
    """
    global _current_key_index
    _current_key_index = (_current_key_index + 1) % len(_clients)
    return _current_key_index != 0


def _is_quota_error(exc: Exception) -> bool:
    """يكتشف لو الخطأ بسبب حد التوكنات/الكوتة تحديداً (مو خطأ آخر غير مرتبط بالمفتاح)."""
    msg = str(exc).lower()
    return any(s in msg for s in ["429", "rate_limit", "quota", "tokens per minute", "request too large"])



BASE_SYSTEM = """You are an elite Senior Frontend Engineer, Game Developer, and UI/UX Designer AI. You think deeply before coding: you infer the user's true intent, including features they implied but didn't explicitly state.

OUTPUT CONTRACT — NEVER VIOLATE:
Return ONLY a raw JSON object. No markdown. No backticks. No explanation.
First char = {   Last char = }

JSON STRUCTURE:
{"projectName": "kebab-case-max-30-chars", "files": [{"path": "index.html", "content": "..."}, {"path": "style.css", "content": "..."}, {"path": "script.js", "content": "..."}]}

TECHNOLOGY RULES:
- Pure vanilla HTML5 + CSS3 + ES6 JS ONLY. NO React/Vue/npm/imports.
- Tailwind v4 CDN in index.html: <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
- index.html must link style.css and script.js properly.

SCOPE RULE — THE MOST IMPORTANT RULE, NEVER VIOLATE:
Build EXACTLY what the user asked for — nothing more, nothing less.
- If the user asked for a simple page (logo, title, background, animation), build ONLY that. Do NOT add
  products, categories, a cart, prices, or any e-commerce elements unless the user explicitly asked for
  a store/shop/products.
- Do NOT assume a brand name implies a store. A name + logo + background request is a simple branded
  page, not an e-commerce site, unless words like "متجر" (store) / "منتجات" (products) / "بيع" (sell) /
  "اقسام" (categories) / "سلة" (cart) actually appear in the request.
- The E-COMMERCE MANDATORY LOGIC section below applies ONLY when the user's request clearly describes
  a store with products to sell. For every other request, ignore that section completely.

DEEP UNDERSTANDING — THINK LIKE A PRODUCT OWNER (applies only within what was actually requested):
- "Store/متجر" implies: working cart, category nav, product images, prices, checkout — even if unstated
- "Game/لعبة" implies: score, win/lose, restart button
- "Dashboard" implies: charts, stat cards, sidebar
- Vague wording ("خله احلى") = visual polish only, never change structure
- "غير اللون" without specifying = apply to primary brand color consistently
- Never silently delete a feature the user didn't ask to remove
- Never silently ADD a feature/section/category the user didn't ask for, even if it "feels natural"

DESIGN: premium gradients, glassmorphism, animations, hover states, dark theme default, fully responsive.
ARABIC: Arabic request = dir="rtl" lang="ar", Cairo/Tajawal font.

CONTENT: Implement every feature mentioned or implied. Realistic content, real product names/prices —
but ONLY if a store was actually requested (see SCOPE RULE above).
Stores: product photos from https://picsum.photos/seed/SEEDNAME/400/500 (unique seed each).

E-COMMERCE MANDATORY LOGIC (ONLY IF a store/products/cart was explicitly requested — otherwise skip entirely):
- ALL products in one JS array {id,name,category,price,image}
- Category buttons filter the SAME array via one shared function — never separate disconnected sections
- Real cart state (let cart=[]), add-to-cart updates visible badge count
- Cart icon top-left opens panel with items/remove/subtotal/checkout button
- Checkout: address input, order summary, Apple Pay styled button (visual simulation only, never real payment)
- Every step must work with zero dead buttons

REAL LINKS RULE: If real links are provided under "روابط حقيقية" in the request, use them EXACTLY as given —
never invent alternative URLs. For YouTube links, convert watch?v=ID to embed/ID inside an <iframe>.
For other links, use plain <a href> tags with the provided titles.

FORBIDDEN: placeholder text like "Product 1"/"Lorem ipsum", stub functions, broken category filters,
fake payment claims, AND adding any store/product/cart elements when none were requested."""


BUILD_PROMPT = """Build a complete, production-ready website.

REQUEST: {request}

CRITICAL RULE: Only build EXACTLY what the user asked for — nothing more.
- If the request does NOT explicitly mention a store/products/cart/categories, do NOT add any of them.
  A request for a logo + name + background animation is a simple branded page, not a store.
- If they DID specify a product category (e.g. electronics), every product/section must belong to
  that category — never invent unrelated categories or products.
- Fill in realistic details (names, prices, images) WITHIN what was requested, never outside its scope.

Implement every feature fully. Premium design. Arabic = RTL + Cairo font.
Only add cart/filters/checkout if the request is actually a store.

Return ONLY the JSON object."""


EDIT_PROMPT = """Modify this existing website. Understand it before changing anything.

SUMMARY: {code_summary}

CURRENT CODE:
{current_code}

EDIT REQUEST: {edit_request}

Apply the change completely across all files that need it. Never remove a working feature unless asked.
Return ALL 3 files complete, even unchanged ones. Return ONLY the JSON object."""


# ─────────────────────────────────────────────
# Code compression — critical for staying under Groq free-tier TPM limit
# ─────────────────────────────────────────────
def compress_code_for_prompt(current_code: str, max_chars: int = 7000) -> str:
    """
    يضغط الكود الحالي قبل إرساله لتقليل استهلاك التوكنات (حد Groq المجاني: 12000 توكن/دقيقة).
    يحذف المسافات الزائدة بدون كسر بنية الكود، ويقتطع الزيادة مع تنبيه واضح للنموذج.
    """
    if not current_code:
        return current_code
    compressed = re.sub(r"[ \t]{2,}", " ", current_code)
    compressed = re.sub(r"\n{3,}", "\n\n", compressed)
    if len(compressed) <= max_chars:
        return compressed
    return compressed[:max_chars] + "\n\n[...الباقي مقتطع لتجاوز الحد. حافظ على ما لم يظهر كاملاً كما هو.]"


def summarize_code(current_code: str) -> str:
    """تلخيص سريع للكود الحالي بدون استدعاء AI إضافي."""
    if not current_code or len(current_code.strip()) < 20:
        return "لا يوجد كود سابق — مشروع جديد بالكامل."
    lower = current_code.lower()
    features = []
    checks = [
        (["cart", "سلة"], "سلة تسوق"),
        (["category", "قسم", "filter"], "فلترة/أقسام"),
        (["apple pay", "checkout", "دفع"], "صفحة دفع"),
        (["score", "game"], "منطق لعبة"),
        (["chart", "canvas"], "رسوم بيانية"),
        (["cairo", 'dir="rtl"'], "موقع عربي RTL"),
    ]
    for keywords, label in checks:
        if any(k in lower for k in keywords):
            features.append(label)
    return f"الميزات الحالية: {', '.join(features)}." if features else "موقع بسيط."


def classify_edit_intent(edit_request: str) -> str:
    """تصنيف سريع لنوع طلب التعديل."""
    vague_markers = ["احلى", "افضل", "حسن", "طور", "زيد شي", "ضيف شي"]
    if any(m in edit_request for m in vague_markers) and len(edit_request.split()) < 5:
        return "vague_polish"
    if any(w in edit_request for w in ["حذف", "شيل", "ازل", "remove", "delete"]):
        return "removal"
    if any(w in edit_request for w in ["لون", "تصميم", "شكل", "خط", "style", "color"]):
        return "style_only"
    if any(w in edit_request for w in ["لا يعمل", "ما يعمل", "خطأ", "مشكلة", "bug", "fix"]):
        return "bug_fix"
    return "feature_or_content"


def extract_dominant_color(image_path: str) -> Optional[str]:
    """يستخرج اللون السائد من صورة محلية (hex code) — الموديل نصي ولا يرى الصورة فعلياً."""
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
    """تعليمات مختصرة للـ AI عن الصورة المرفقة — مضغوطة لتقليل التوكنات."""
    if not image_url:
        return ""
    dominant = extract_dominant_color(image_path) if image_path else None
    block = f"\n\n[صورة مرفقة: {image_url}]"
    if dominant:
        block += f" [لون سائد: {dominant}]"
    block += (
        " لوقو=استخدم الرابط كـ src للوقو في index.html. "
        "لون الصفحة=طبّق اللون السائد على العناصر الأساسية بـ style.css. "
        "صورة منتج معيّن=غيّر فقط image لذلك المنتج بمصفوفة script.js."
    )
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
        if len(f.get("content", "").strip()) < 50:
            raise ValueError(f"Content too short in {f.get('path')}")


def _looks_like_store(text: str) -> bool:
    """
    يفحص كلمات دالة على متجر/منتجات بحدود كلمة كاملة لتجنّب إيجابيات خاطئة
    (مثل "محلي" أو "تسوقها" تطابق جزئياً مع "محل"/"تسوق" لو كان الفحص بسيط).
    استُبعدت "محل" من القائمة لأنها كثيرة الالتباس بالعربي (محلي، محلات، بمحل إقامتي...).
    """
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
            client = _get_client()
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.7,
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
                js_content = next((f["content"] for f in data["files"] if f["path"] == "script.js"), "")
                if not _has_cart_logic(js_content):
                    raise ValueError("متجر بدون منطق سلة حقيقي — إعادة المحاولة")

            return extracted

        except json.JSONDecodeError as e:
            last_err = f"JSON error attempt {i}: {e}"
        except ValueError as e:
            last_err = f"Validation error attempt {i}: {e}"
        except Exception as e:
            cause = getattr(e, "__cause__", None)
            cause_info = f" | cause={type(cause).__name__}: {cause}" if cause else ""
            last_err = f"API error attempt {i}: {type(e).__name__}: {e}{cause_info}"
            err_text = str(e).lower()
            if ("429" in err_text or "rate_limit" in err_text or "tokens per minute" in err_text) and len(_clients) > 1:
                _rotate_key()

        if i < retries:
            time.sleep(3 * i)

    raise RuntimeError(f"Groq failed {retries}x across {len(_clients)} key(s). Last: {last_err} | raw[:300]={(last_raw or '')[:300]}")


PLANNING_SYSTEM = """أنت مساعد تخطيط مواقع ودود. مهمتك محصورة بهذي الخطوة فقط:
1. تفهم فكرة الموقع من كلام المستخدم بدقة، بدون تخترع تفاصيل لم يذكرها.
2. تردّ بإيجاز (2-4 جمل) تلخّص فهمك وتسأل عن أي تفصيل مهم ناقص (نوع المنتجات، الألوان، الأقسام، الميزات).
3. لا تكتب أي كود أبداً في هذه المرحلة — فقط محادثة نصية.
4. حلّل آخر رسالة من المستخدم: هل فيها نية واضحة أنه جاهز للبناء الآن (مثل: يلا، ابدأ، سويها، انشرها، تمام كذا، جاهز، ماشي ابدأ)؟
   - لو نعم: ابدأ ردك بالضبط بـ "[READY]" ثم رسالة قصيرة تؤكد إنك بادئ البناء الآن.
   - لو لا (لسه يشرح/يضيف تفاصيل أو يسأل): ابدأ ردك بـ "[CONTINUE]" ثم ردك التفاعلي العادي.
هذا التصنيف [READY] أو [CONTINUE] إلزامي في أول كلمة من ردك دائماً."""


def plan_chat(conversation: list) -> tuple[str, bool]:
    """
    محادثة تخطيط قبل البناء — تحلل كامل السياق وتقرر هل المستخدم جاهز للبناء الآن أو لسه يوضّح.
    conversation: قائمة [{"role": "user"/"assistant", "content": "..."}] بكامل تاريخ محادثة التخطيط.
    يرجع (نص الرد للمستخدم, جاهز_للبناء: bool).
    """
    messages = [{"role": "system", "content": PLANNING_SYSTEM}] + conversation

    last_err = None
    for i in range(1, 4):
        try:
            client = _get_client()
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.5,
                max_tokens=300,
            )
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("[READY]"):
                return raw.replace("[READY]", "", 1).strip(), True
            if raw.startswith("[CONTINUE]"):
                return raw.replace("[CONTINUE]", "", 1).strip(), False
            # لو ما التزم بالتصنيف، نعتبره استمرار محادثة عادي (أأمن افتراض)
            return raw, False
        except Exception as e:
            last_err = e
            err_text = str(e).lower()
            if ("429" in err_text or "rate_limit" in err_text) and len(_clients) > 1:
                _rotate_key()
            time.sleep(2 * i)

    raise RuntimeError(f"Groq planning chat failed: {last_err}")


def needs_real_links(conversation_text: str) -> Optional[str]:
    """
    يكتشف لو المستخدم يطلب محتوى يحتاج روابط حقيقية فعلية (فيديوهات، مواقع، مراجع)
    ويرجع استعلام بحث مناسب، أو None لو الطلب لا يحتاج بحثاً حقيقياً.
    اكتشاف بسيط بالكلمات المفتاحية — كافٍ هنا لأن التكلفة (استدعاء بحث خاطئ) منخفضة.
    """
    triggers = [
        "فيديو", "فيديوهات", "يوتيوب", "youtube", "رابط حقيقي", "روابط حقيقية",
        "منافس", "منافسين", "مواقع تشبه", "أمثلة حقيقية", "حط لي روابط",
        "اعطني روابط", "اعطيني روابط", "افضل", "best", "top",
    ]
    if any(t in conversation_text for t in triggers):
        return conversation_text[-200:]  # آخر جزء من المحادثة كاستعلام تقريبي
    return None


def build_from_conversation(conversation: list) -> str:
    """
    يبني الموقع من كامل محادثة التخطيط (مو من رسالة واحدة) — يضمن عدم اختراع تفاصيل
    لم يذكرها المستخدم عبر كل المحادثة، ويستخدم كل ما قاله حرفياً كمتطلبات.
    لو الطلب يحتاج روابط حقيقية (فيديوهات/مواقع)، يبحث عنها فعلياً قبل البناء ويحقنها بالـ prompt.

    ملاحظة مهمة: نأخذ فقط رسائل المستخدم (نتجاهل ردود البوت التوضيحية) ونحدّ طولها،
    لأن محادثات طويلة جداً تكبّر الـ prompt وتجعل Groq يقطع مخرجات الملفات قبل اكتمالها
    (سبب شائع لخطأ "Content too short in style.css").
    """
    user_only = [m["content"] for m in conversation if m["role"] == "user"]
    full_request = "\n".join(user_only)

    # لو المحادثة طويلة جداً، نقتصر على أهم جزء (أول رسالة فيها الفكرة + آخر 3 رسائل توضيح)
    if len(user_only) > 5:
        trimmed = [user_only[0]] + user_only[-3:]
        full_request = "\n".join(trimmed)

    links_block = ""
    if web_search.is_search_available():
        search_query = needs_real_links(full_request)
        if search_query:
            results = web_search.search_real_links(search_query, max_results=5)
            links_block = web_search.format_links_for_prompt(results)

    prompt = BUILD_PROMPT.format(request=full_request) + (
        "\n\nمهم جداً جداً: التزم حرفياً بكل ما ورد أعلاه فقط، بدون أي زيادة. "
        "إذا لم يذكر المستخدم صراحة كلمة متجر/منتجات/سلة/أقسام، فهذا طلب صفحة بسيطة فقط "
        "(مثل شعار + اسم + خلفية) — لا تضف أي منتجات أو أقسام أو سلة تسوق من عندك أبداً. "
        "إذا ذكر المستخدم نوع منتجات معيّن (مثل إلكترونيات)، يجب أن تكون كل المنتجات في هذا الموقع "
        "من هذا النوع فقط، ولا تخترع أقسام أو منتجات من نوع مختلف."
    ) + links_block

    return _call(prompt, check_store=_looks_like_store(full_request))


def builder(request: str) -> str:
    return _call(BUILD_PROMPT.format(request=request), check_store=_looks_like_store(request))


def editor(
    edit_request: str,
    current_code: str = "",
    image_url: Optional[str] = None,
    image_path: Optional[str] = None,
) -> str:
    summary = summarize_code(current_code)
    intent = classify_edit_intent(edit_request)
    compressed_code = compress_code_for_prompt(current_code)

    intent_hints = {
        "vague_polish": "[نية: تحسين بصري فقط، لا تغيّر البنية]",
        "removal": "[نية: حذف دقيق دون التأثير على باقي الميزات]",
        "style_only": "[نية: تصميم/ألوان فقط، لا تغيّر المنطق]",
        "bug_fix": "[نية: تصحيح خطأ دون كسر شيء يعمل]",
        "feature_or_content": "[نية: إضافة ميزة/محتوى متكامل]",
    }
    image_instruction = _build_image_instruction(image_url, image_path)
    enriched_request = f"{edit_request} {intent_hints.get(intent, '')}{image_instruction}"

    return _call(
        EDIT_PROMPT.format(
            current_code=compressed_code or "(no source — new project)",
            code_summary=summary,
            edit_request=enriched_request,
        ),
        check_store=_looks_like_store(current_code + edit_request),
    )


def planner(text: str) -> str: return builder(text)
def coder(plan: str) -> str:   return plan
def reviewer(code: str) -> str: return code

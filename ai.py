"""
ai.py — محرك بناء وتعديل المشاريع بالذكاء الاصطناعي — النسخة المطورة.

المحركات المدعومة:
  - Groq (Llama 3.3 70B) — الأسرع للبناء
  - Anthropic Claude — للمشاريع المعقدة والألعاب
  - تناوب تلقائي بين المحركين عند الفشل

أنواع المشاريع:
  - website   : مواقع احترافية
  - game      : ألعاب كاملة قابلة للعب
  - dashboard : لوحات تحكم تفاعلية
  - store     : متاجر إلكترونية كاملة
  - landing   : صفحات هبوط
  - portfolio : ملفات أعمال
  - app       : تطبيقات ويب
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

GROQ_MODEL      = "llama-3.3-70b-versatile"
ANTHROPIC_MODEL = "claude-sonnet-4-6"

# ─── Groq Key Rotation ───────────────────────
_GROQ_KEYS = []
_first = os.getenv("GROQ_API_KEY")
if _first and _first.strip():
    _GROQ_KEYS.append(_first.strip())
for _i in range(2, 11):
    _k = os.getenv(f"GROQ_API_KEY_{_i}")
    if _k and _k.strip():
        _GROQ_KEYS.append(_k.strip())

if not _GROQ_KEYS:
    raise RuntimeError("لا يوجد GROQ_API_KEY في متغيرات البيئة!")

_groq_clients = [
    Groq(api_key=k, timeout=60.0, http_client=httpx.Client(http2=False))
    for k in _GROQ_KEYS
]
_groq_idx = 0

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")


def _get_groq():
    return _groq_clients[_groq_idx]


def _rotate_groq() -> bool:
    global _groq_idx
    _groq_idx = (_groq_idx + 1) % len(_groq_clients)
    return _groq_idx != 0


def _is_quota_err(e: Exception) -> bool:
    msg = str(e).lower()
    return any(s in msg for s in ["429", "rate_limit", "quota", "tokens per minute", "request too large"])


# ═══════════════════════════════════════════════════════════════════
# BASE_SYSTEM — تعليمات عامة لكل أنواع المشاريع
# ═══════════════════════════════════════════════════════════════════
BASE_SYSTEM = """You are an elite Full-Stack AI Engineer, Creative Director, Game Developer, and UX Specialist.
You don't build templates — you build custom digital products tailored to each request.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT CONTRACT — NEVER VIOLATE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Return ONLY raw JSON. No markdown. No backticks. No explanation.
First char = {   Last char = }

REQUIRED JSON STRUCTURE:
{
  "projectName": "kebab-case-max-30-chars",
  "projectType": "website|game|dashboard|store|landing|portfolio|app",
  "files": [
    {"path": "index.html", "content": "..."},
    {"path": "style.css",  "content": "..."},
    {"path": "script.js",  "content": "..."}
  ]
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TECHNOLOGY RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Vanilla HTML5 + CSS3 + ES6+ ONLY. No React/Vue/npm.
- Tailwind v4 CDN: <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
- index.html MUST link: <link rel="stylesheet" href="style.css"> and <script src="script.js" defer></script>
- Google Fonts via CDN. Arabic: Cairo + Tajawal. Latin: Inter + Poppins.
- Chart.js: <script src="https://cdn.jsdelivr.net/npm/chart.js"></script> (for dashboards)
- Howler.js: <script src="https://cdnjs.cloudflare.com/ajax/libs/howler/2.2.3/howler.min.js"></script> (for games with sound)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCOPE RULE — ABSOLUTE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Build EXACTLY what was requested — nothing more, nothing less.
Never add store/cart/shop elements unless explicitly requested.
Never add game logic unless a game was requested.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PREMIUM DESIGN SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COLORS:
- Rich dark theme default: bg #0a0a0f, cards rgba(255,255,255,0.04)
- Brand accent: electric blue #6366f1 | emerald #10b981 | amber #f59e0b | rose #f43f5e | violet #8b5cf6
- Gradients: always multi-stop. e.g: linear-gradient(135deg, #667eea 0%, #764ba2 100%)
- Glassmorphism: background rgba(255,255,255,0.05); backdrop-filter blur(20px); border 1px solid rgba(255,255,255,0.1)

ANIMATIONS (mandatory):
- Page load: fade-in + slide-up, staggered 0.1s delays
- IntersectionObserver for scroll animations
- Buttons: scale(1.05) + glow on hover
- Cards: translateY(-8px) + shadow on hover
- Scroll progress bar at top (2px colored line)
- html { scroll-behavior: smooth }

LAYOUT:
- Mobile-first, responsive. Breakpoints: 640/768/1024/1280px
- CSS Grid for complex, Flexbox for alignment
- Max content width: 1200px centered
- Generous whitespace

CONTENT:
- Arabic sites: realistic Arabic names/content, SAR prices, dir="rtl"
- Never Lorem ipsum
- picsum.photos for placeholder images (different seed per image)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
E-COMMERCE (only when explicitly requested)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Products JS array: {id, name, category, price, image, description, rating}
- let cart = [] persisted to localStorage
- Cart badge count, slide-in panel, checkout form
- All buttons functional — zero dead UI

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DASHBOARD (when requested)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Sidebar with nav + active states
- Stat cards with animated counters
- Chart.js charts (line, bar, doughnut)
- Data tables with sorting
- All interactive

FORBIDDEN: Lorem ipsum, placeholder text, stub functions, broken features, empty script.js"""


# ═══════════════════════════════════════════════════════════════════
# GAME_SYSTEM — نظام الألعاب المتخصص
# ═══════════════════════════════════════════════════════════════════
GAME_SYSTEM = """You are a world-class HTML5 Game Developer specializing in browser games.
You build COMPLETE, FULLY PLAYABLE games — not demos, not mockups.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT CONTRACT — SAME AS BASE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Return ONLY raw JSON. projectType must be "game".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GAME REQUIREMENTS (ALL MANDATORY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ COMPLETE GAME LOGIC — every rule implemented, no stubs
✅ WORKING WIN/LOSE conditions with clear messages
✅ SCORE SYSTEM — real-time score display + high score in localStorage
✅ LIVES/HEALTH system where applicable
✅ LEVEL PROGRESSION or difficulty increase
✅ PAUSE/RESUME functionality (P key or button)
✅ RESTART button always visible and working
✅ SMOOTH ANIMATIONS at 60fps using requestAnimationFrame
✅ KEYBOARD + TOUCH controls (mobile-friendly)
✅ SOUND EFFECTS using Web Audio API (not external files needed)
✅ START SCREEN with game title, instructions, and Play button
✅ GAME OVER SCREEN with score, high score, and Play Again button

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GAME TYPES — FULL IMPLEMENTATION GUIDE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PUZZLE GAMES (Sudoku, Blockudoku, 2048, etc.):
- Complete board generation algorithm
- All validation rules (Sudoku: row/col/box uniqueness)
- Hint system
- Undo last move
- Timer display
- Difficulty levels (Easy/Medium/Hard)
- Auto-save progress in localStorage
- Blockudoku: piece dragging, block placement validation, line clearing, score multipliers

ACTION/ARCADE (Snake, Tetris, Breakout, etc.):
- Canvas-based rendering for performance
- Proper collision detection
- Speed increase over time
- Power-ups/bonuses
- Particle effects on destruction/collection

CARD/BOARD GAMES:
- Full deck/board generation
- AI opponent with basic strategy
- Move validation
- Win detection

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GAME UI DESIGN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Dark theme with neon accent colors
- Score/level prominently displayed
- Smooth CSS transitions for board updates
- Mobile touch support (touchstart/touchend/touchmove)
- Responsive canvas or grid that fits screen

ABSOLUTELY FORBIDDEN in games:
- Incomplete game logic (e.g. Sudoku without validation)
- Alert() for game messages — use styled HTML overlays
- Dead buttons that do nothing
- Missing win/lose detection
- Non-working controls"""


# ═══════════════════════════════════════════════════════════════════
# PLANNING_SYSTEM — محادثة التخطيط الذكية
# ═══════════════════════════════════════════════════════════════════
PLANNING_SYSTEM = """أنت مستشار مواقع وتطبيقات ذكي وخبير في UX وبناء المنتجات الرقمية.
مهمتك: تفهم بعمق ما يريده المستخدم وتساعده يوضح فكرته قبل البناء.

قواعد المحادثة:
1. حلّل نوع المشروع: موقع؟ لعبة؟ متجر؟ داشبورد؟ تطبيق؟ بورتفوليو؟
2. اسأل عن التفاصيل الناقصة المهمة فقط (سؤال واحد في كل مرة):
   - متجر   → نوع المنتجات؟ أقسام؟ سلة تسوق كاملة؟
   - لعبة   → نوع اللعبة؟ موبايل أو كمبيوتر؟ مستوى الصعوبة؟
   - بورتفوليو → مجاله؟ نماذج أعماله؟ نموذج تواصل؟
   - صفحة هبوط → المنتج/الخدمة؟ الجمهور؟ هدف الـ CTA؟
   - داشبورد → نوع البيانات؟ أي رسوم بيانية؟
3. اقترح ميزة ذكية واحدة بناءً على فهمك (اذكر إنها اقتراح).
4. لا تكتب أي كود — محادثة نصية فقط.
5. ردودك مختصرة ومباشرة (2-4 جمل).

قرار الجاهزية:
- هل المستخدم أعطى نية واضحة للبدء؟ (يلا / ابدأ / سويها / تمام / جاهز / ماشي / اعملها / انشر)
- نعم → ابدأ بـ [READY] ثم جملة تأكيد لما ستبنيه
- لا  → ابدأ بـ [CONTINUE] ثم ردك الطبيعي

[READY] أو [CONTINUE] في أول الرد دائماً — إلزامي بدون استثناء."""


# ─── Build Prompts ────────────────────────────
BUILD_PROMPT = """Build a complete, production-ready, visually stunning project.

REQUEST: {request}

PROJECT TYPE DETECTED: {project_type}

CRITICAL RULES:
- Build ONLY what was explicitly requested
- No store/cart unless asked for a store
- No game logic unless a game was requested
- Use the correct projectType in the JSON

QUALITY CHECKLIST:
✓ Premium dark design with gradients and glassmorphism
✓ Scroll-triggered animations via IntersectionObserver
✓ Button + card hover effects
✓ Fully responsive mobile → desktop
✓ Realistic Arabic content (no Lorem ipsum)
✓ All interactive elements work
✓ script.js has scroll progress bar + animations

Return ONLY the JSON object."""


GAME_BUILD_PROMPT = """Build a COMPLETE, FULLY PLAYABLE {game_type} game.

REQUEST: {request}

MANDATORY GAME FEATURES:
✓ Complete game logic (all rules, no stubs)
✓ Win/Lose detection with styled overlays
✓ Real-time score + localStorage high score
✓ Pause/Resume (P key + button)
✓ Restart button
✓ 60fps animation loop
✓ Keyboard + touch controls
✓ Web Audio API sound effects
✓ Start screen + Game Over screen
✓ Mobile responsive

SPECIFIC REQUIREMENTS:
{specific_requirements}

Return ONLY the JSON object with projectType="game"."""


EDIT_PROMPT = """You are editing an existing project. Understand the current code fully before making changes.

PROJECT SUMMARY: {code_summary}
CURRENT CODE:
{current_code}

EDIT REQUEST: {edit_request}

EDITING RULES:
1. Apply ONLY the requested change — never touch unrelated parts
2. Never remove working features unless explicitly asked
3. Match existing design language exactly
4. Return ALL files complete (even unchanged ones)
5. Preserve all animations and interactions unless asked to change them
6. For games: never break game logic when making visual changes

Return ONLY the JSON object."""


# ─── Utility Functions ────────────────────────
def _detect_project_type(text: str) -> str:
    """يكتشف نوع المشروع من نص الطلب."""
    text_lower = text.lower()
    game_kw    = ["لعبة", "game", "العب", "بلوكودوكو", "سودوكو", "سنيك", "تيتريس",
                  "blockudoku", "sudoku", "snake", "tetris", "2048", "ميمورى", "memory",
                  "puzzle", "arcade", "breakout", "pacman", "بازل", "قيم", "gaming"]
    store_kw   = ["متجر", "store", "shop", "منتجات", "سلة", "cart", "تسوق", "بيع", "ecommerce"]
    dash_kw    = ["داشبورد", "dashboard", "لوحة تحكم", "إحصائيات", "تقارير", "charts", "analytics"]
    landing_kw = ["صفحة هبوط", "landing", "لانج", "landing page", "هبوط"]
    port_kw    = ["بورتفوليو", "portfolio", "أعمالي", "معرض أعمال", "سيرة ذاتية", "cv"]
    app_kw     = ["تطبيق", "app", "application", "حجز", "booking", "نموذج", "form", "حاسبة", "calculator"]

    if any(k in text_lower for k in game_kw):    return "game"
    if any(k in text_lower for k in store_kw):   return "store"
    if any(k in text_lower for k in dash_kw):    return "dashboard"
    if any(k in text_lower for k in landing_kw): return "landing"
    if any(k in text_lower for k in port_kw):    return "portfolio"
    if any(k in text_lower for k in app_kw):     return "app"
    return "website"


def _detect_game_type(text: str) -> tuple[str, str]:
    """يكتشف نوع اللعبة ومتطلباتها الخاصة."""
    text_lower = text.lower()

    games = {
        "blockudoku": ("Blockudoku", """
- 9x9 grid with 3x3 section highlighting
- 3 random pieces shown at bottom, drag to place
- Clear complete rows, columns, AND 3x3 boxes
- Score multipliers for multiple clears at once
- Combo system
- Piece preview with ghost placement
- Game over when no piece can be placed"""),
        "sudoku": ("Sudoku", """
- 9x9 grid with 3x3 box borders (thicker lines)
- 3 difficulty levels: Easy(35 given)/Medium(27)/Hard(20)
- Number pad 1-9 + Erase button
- Highlight related cells on selection
- Error detection (mark wrong numbers red)
- Hint system (reveal one cell)
- Timer + undo last move
- Auto-save current puzzle in localStorage"""),
        "2048": ("2048", """
- 4x4 grid with smooth slide animations
- Arrow keys + swipe gestures
- Merge tiles animation + score popup
- New random tile after each move
- Win at 2048 but allow continuing
- Best score in localStorage"""),
        "snake": ("Snake", """
- Canvas-based smooth movement
- Arrow keys + WASD + swipe
- Food spawns avoiding snake body
- Speed increases every 5 food items
- Wall wrap-around option
- Particle effect on eating food"""),
        "tetris": ("Tetris", """
- All 7 tetromino pieces with correct colors
- Wall kicks for rotation
- Ghost piece (semi-transparent preview)
- Hold piece feature
- Next piece preview (show next 3)
- Line clear animation
- Increasing speed per level
- T-spin detection bonus"""),
        "memory": ("Memory Match", """
- 4x4 or 6x6 grid of cards
- Flip animation (3D CSS transform)
- Match detection + lock matched pairs
- Attempt counter + timer
- Shuffle on restart
- Win screen with stats"""),
    }

    for key, (name, reqs) in games.items():
        if key in text_lower:
            return name, reqs

    # لعبة عامة
    return "Browser Game", """
- Complete game loop (start → play → win/lose → restart)
- Score system
- Increasing difficulty
- Mobile-friendly controls"""


def compress_code_for_prompt(current_code: str, max_chars: int = 8000) -> str:
    if not current_code:
        return current_code
    compressed = re.sub(r"[ \t]{2,}", " ", current_code)
    compressed = re.sub(r"\n{3,}", "\n\n", compressed)
    if len(compressed) <= max_chars:
        return compressed
    return compressed[:max_chars] + "\n\n[...مقتطع — احتفظ بكل ما لم يظهر كما هو]"


def summarize_code(current_code: str) -> str:
    if not current_code or len(current_code.strip()) < 20:
        return "مشروع جديد — لا يوجد كود سابق."
    lower = current_code.lower()
    features = []
    checks = [
        (["cart", "سلة", "addtocart"],          "سلة تسوق"),
        (["game", "score", "canvas", "لعبة"],   "لعبة"),
        (["chart", "canvas", "chartjs"],        "رسوم بيانية"),
        (["cairo", 'dir="rtl"'],                "RTL عربي"),
        (["intersectionobserver"],              "أنيميشن تمرير"),
        (["localstorage"],                       "تخزين محلي"),
        (["fetch(", "xmlhttprequest"],           "طلبات API"),
        (["modal", "dialog"],                    "نوافذ منبثقة"),
        (["sidebar", "dashboard"],               "داشبورد"),
        (["audio", "howler", "webaudio"],       "صوت"),
    ]
    for keywords, label in checks:
        if any(k in lower for k in keywords):
            features.append(label)
    title_m = re.search(r"<title>(.*?)</title>", current_code, re.IGNORECASE)
    title = f" | {title_m.group(1)}" if title_m else ""
    return f"الميزات: {', '.join(features)}{title}." if features else f"موقع بسيط{title}."


def classify_edit_intent(edit_request: str) -> str:
    vague = ["احلى", "افضل", "حسن", "طور", "جمّل", "حسّن", "اجمل"]
    if any(m in edit_request for m in vague) and len(edit_request.split()) < 6:
        return "vague_polish"
    if any(w in edit_request for w in ["حذف", "شيل", "ازل", "امسح", "remove", "delete"]):
        return "removal"
    if any(w in edit_request for w in ["لون", "تصميم", "خط", "خلفية", "color", "font", "background"]):
        return "style_only"
    if any(w in edit_request for w in ["لا يعمل", "خطأ", "مشكلة", "bug", "fix", "error"]):
        return "bug_fix"
    if any(w in edit_request for w in ["dark mode", "دارك", "مظلم"]):
        return "theme_change"
    if any(w in edit_request for w in ["تسجيل دخول", "login", "auth", "سجل"]):
        return "add_auth"
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
        block += f" [اللون السائد: {dominant} — استخدمه لوناً أساسياً]"
    block += (
        " لو لوقو: ضعها <img src='{url}'> في الهيدر height 60-80px. "
        "لو منتج: غيّر image لهذا المنتج فقط. "
        "لو خلفية: ضعها background-image في hero section."
    ).replace("{url}", image_url)
    return block


# ─── JSON Parsing ─────────────────────────────
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
        if esc:   esc = False; continue
        if c == "\\" and in_str: esc = True; continue
        if c == '"': in_str = not in_str; continue
        if in_str: continue
        if c == "{": depth += 1
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


def _validate(data: dict, is_game: bool = False) -> None:
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
        if path == "script.js" and not is_game:
            continue
        if is_game and path == "script.js" and len(content.strip()) < 500:
            raise ValueError(f"Game script.js too short ({len(content.strip())} chars) — incomplete game logic")
        if len(content.strip()) < 10:
            raise ValueError(f"Content empty in {path}")


def _check_game_quality(js: str) -> tuple[bool, list]:
    """يفحص جودة كود اللعبة ويرجع (اجتاز, قائمة_المشاكل)."""
    issues = []
    min_checks = [
        ("requestAnimationFrame", "لا يوجد animation loop"),
        ("score", "لا يوجد نظام نقاط"),
        ("restart", "لا يوجد زر إعادة تشغيل"),
        ("localStorage", "لا يوجد حفظ للأعلى"),
    ]
    for keyword, msg in min_checks:
        if keyword.lower() not in js.lower():
            issues.append(msg)
    passed = len(issues) == 0
    return passed, issues


# ─── Groq API Call ────────────────────────────
def _groq_call(prompt: str, system: str = None, retries: int = 5,
               is_game: bool = False) -> str:
    last_err = last_raw = None
    sys = system or BASE_SYSTEM
    messages = [
        {"role": "system", "content": sys},
        {"role": "user",   "content": prompt},
    ]

    for i in range(1, retries + 1):
        try:
            resp = _get_groq().chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                temperature=0.45 if not is_game else 0.35,
                max_tokens=8000,
                response_format={"type": "json_object"},
            )
            last_raw = resp.choices[0].message.content.strip()
            extracted = _extract_json(last_raw)
            try:
                data = json.loads(extracted)
            except json.JSONDecodeError:
                data = json.loads(_fix_json(extracted))

            _validate(data, is_game=is_game)

            if is_game:
                js = next((f["content"] for f in data["files"] if f["path"] == "script.js"), "")
                ok, issues = _check_game_quality(js)
                if not ok:
                    raise ValueError(f"جودة اللعبة غير كافية: {issues}")

            return extracted

        except json.JSONDecodeError as e:
            last_err = f"JSON error attempt {i}: {e}"
        except ValueError as e:
            last_err = f"Validation attempt {i}: {e}"
        except Exception as e:
            last_err = f"API error attempt {i}: {type(e).__name__}: {e}"
            if _is_quota_err(e) and len(_groq_clients) > 1:
                _rotate_groq()

        if i < retries:
            time.sleep(3 * i)

    raise RuntimeError(f"Groq failed {retries}x. Last: {last_err} | raw={last_raw}")


# ─── Anthropic API Call (للمشاريع المعقدة) ───
def _anthropic_call(prompt: str, system: str = None, is_game: bool = False) -> str:
    if not ANTHROPIC_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY غير مضبوط")

    import httpx as _httpx
    sys = system or BASE_SYSTEM

    resp = _httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key":        ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type":     "application/json",
        },
        json={
            "model":      ANTHROPIC_MODEL,
            "max_tokens": 8000,
            "system":     sys,
            "messages":   [{"role": "user", "content": prompt}],
        },
        timeout=120.0,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"Anthropic API error: {resp.status_code} — {resp.text[:300]}")

    content = resp.json()["content"][0]["text"]
    extracted = _extract_json(content)
    try:
        data = json.loads(extracted)
    except json.JSONDecodeError:
        data = json.loads(_fix_json(extracted))

    _validate(data, is_game=is_game)
    return extracted


def _call_with_fallback(prompt: str, system: str = None, is_game: bool = False,
                        retries: int = 4) -> str:
    """يجرب Groq أولاً، ثم Anthropic عند الفشل."""
    try:
        return _groq_call(prompt, system=system, retries=retries, is_game=is_game)
    except RuntimeError as groq_err:
        if ANTHROPIC_KEY:
            from logger import log
            log(f"[AI_FALLBACK] Groq فشل، جاري المحاولة مع Anthropic: {groq_err}")
            return _anthropic_call(prompt, system=system, is_game=is_game)
        raise


# ══════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════
def plan_chat(conversation: list) -> tuple[str, bool]:
    """محادثة تخطيط ذكية — يرجع (نص_الرد, جاهز_للبناء)."""
    messages = [{"role": "system", "content": PLANNING_SYSTEM}] + conversation
    last_err = None
    for i in range(1, 4):
        try:
            resp = _get_groq().chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                temperature=0.55,
                max_tokens=400,
            )
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("[READY]"):
                return raw.replace("[READY]", "", 1).strip(), True
            if raw.startswith("[CONTINUE]"):
                return raw.replace("[CONTINUE]", "", 1).strip(), False
            return raw, False
        except Exception as e:
            last_err = e
            if _is_quota_err(e) and len(_groq_clients) > 1:
                _rotate_groq()
            time.sleep(2 * i)
    raise RuntimeError(f"plan_chat failed: {last_err}")


def builder(request: str) -> str:
    """يبني مشروعاً جديداً من طلب نصي مباشر."""
    ptype = _detect_project_type(request)
    if ptype == "game":
        return game_builder(request)
    prompt = BUILD_PROMPT.format(request=request, project_type=ptype)
    return _call_with_fallback(prompt)


def game_builder(request: str) -> str:
    """يبني لعبة كاملة قابلة للعب."""
    game_name, game_reqs = _detect_game_type(request)
    prompt = GAME_BUILD_PROMPT.format(
        game_type=game_name,
        request=request,
        specific_requirements=game_reqs,
    )
    return _call_with_fallback(prompt, system=GAME_SYSTEM, is_game=True, retries=5)


def build_from_conversation(conversation: list) -> str:
    """يبني من كامل محادثة التخطيط."""
    user_only = [m["content"] for m in conversation if m["role"] == "user"]
    if len(user_only) > 5:
        user_only = [user_only[0]] + user_only[-3:]
    full_request = "\n".join(user_only)

    ptype = _detect_project_type(full_request)

    # إضافة روابط حقيقية إذا طُلبت
    links_block = ""
    if web_search.is_search_available():
        triggers = ["فيديو", "يوتيوب", "youtube", "رابط حقيقي", "روابط", "أمثلة"]
        if any(t in full_request for t in triggers):
            results = web_search.search_real_links(full_request[-200:], max_results=5)
            links_block = web_search.format_links_for_prompt(results)

    if ptype == "game":
        game_name, game_reqs = _detect_game_type(full_request)
        prompt = GAME_BUILD_PROMPT.format(
            game_type=game_name,
            request=full_request,
            specific_requirements=game_reqs,
        ) + links_block
        return _call_with_fallback(prompt, system=GAME_SYSTEM, is_game=True, retries=5)

    scope = (
        "\n\nقاعدة صارمة: ابنِ حرفياً ما طُلب فقط — لا زيادة ولا نقصان. "
        "لم يذكر متجر/منتجات/سلة → لا تضفها. "
        "ذكر نوع منتجات → كل المحتوى من هذا النوع فقط."
    )
    prompt = BUILD_PROMPT.format(request=full_request, project_type=ptype) + scope + links_block
    return _call_with_fallback(prompt)


def editor(edit_request: str, current_code: str = "",
           image_url: Optional[str] = None, image_path: Optional[str] = None) -> str:
    """يعدّل مشروعاً موجوداً بشكل ذكي."""
    summary    = summarize_code(current_code)
    intent     = classify_edit_intent(edit_request)
    compressed = compress_code_for_prompt(current_code)
    is_game    = "game" in summary.lower() or "لعبة" in summary.lower()

    intent_hints = {
        "vague_polish":  "[نية: تحسين بصري فقط — لا تغيّر المنطق أو البنية]",
        "removal":       "[نية: حذف دقيق — لا تؤثر على الميزات الأخرى]",
        "style_only":    "[نية: تصميم/ألوان فقط — لا تلمس JS]",
        "bug_fix":       "[نية: إصلاح خطأ محدد — لا تعيد هيكلة الكود]",
        "theme_change":  "[نية: تغيير ثيم — طبّق على كل الملفات الثلاثة]",
        "add_auth":      "[نية: إضافة تسجيل دخول — modal مع validation بدون backend حقيقي]",
        "feature_or_content": "[نية: إضافة ميزة/محتوى كامل ومتكامل]",
    }

    img_instr = _build_image_instruction(image_url, image_path)
    enriched  = f"{edit_request} {intent_hints.get(intent, '')}{img_instr}"

    if is_game:
        enriched += "\n[تنبيه: هذا مشروع لعبة — حافظ على كل منطق اللعبة والـ game loop]"

    prompt = EDIT_PROMPT.format(
        current_code=compressed or "(لا يوجد كود — مشروع جديد)",
        code_summary=summary,
        edit_request=enriched,
    )

    system = GAME_SYSTEM if is_game else BASE_SYSTEM
    return _call_with_fallback(prompt, system=system, is_game=is_game)


# دوال للتوافق مع الكود القديم
def planner(text: str) -> str:  return builder(text)
def coder(plan: str)   -> str:  return plan
def reviewer(code: str)-> str:  return code


def needs_real_links(text: str) -> Optional[str]:
    triggers = ["فيديو", "يوتيوب", "youtube", "رابط حقيقي", "روابط حقيقية", "منافس"]
    if any(t in text for t in triggers):
        return text[-200:]
    return None

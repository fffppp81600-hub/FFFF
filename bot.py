"""
bot.py — Telegram bot — النسخة المطورة بالكامل.

ميزات جديدة:
  /help        — شرح كامل
  /my          — مشاريعك مع أزرار تحكم مباشرة
  /cancel      — إلغاء التعديل
  /stats       — إحصائياتك الشخصية
  وضع التعديل — يحتفظ بمحادثة سياقية (multi-turn)
  حماية من الفلود — cooldown ذكي
  رسائل typing — تجربة مستخدم أفضل
  تقسيم الرسائل — لو الرسالة تتجاوز حد تيليغرام
"""
import os
import time
import json
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler, ContextTypes,
    filters, CallbackQueryHandler, CommandHandler
)
from telegram.constants import ChatAction

from ai import builder, editor
from builder import build_project
from deploy import deploy_project, delete_vercel_project
from validator import safe_parse
from store import add_project, get_projects, delete_project
from file_manager import delete_project_files, get_project_files
from logger import log

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ── State ─────────────────────────────────────
_cooldown: dict  = {}   # uid -> last_request_time
EDIT_MODE: dict  = {}   # uid -> project_name
USER_STATS: dict = {}   # uid -> {builds, edits, last_active}


# ── Helpers ───────────────────────────────────
def _allow(uid: str, seconds: int = 8) -> bool:
    now = time.time()
    if now - _cooldown.get(uid, 0) < seconds:
        remaining = int(seconds - (now - _cooldown.get(uid, 0)))
        return False, remaining
    _cooldown[uid] = now
    return True, 0


def _track(uid: str, action: str):
    s = USER_STATS.setdefault(uid, {"builds": 0, "edits": 0, "last_active": ""})
    if action == "build":
        s["builds"] += 1
    elif action == "edit":
        s["edits"] += 1
    s["last_active"] = datetime.now().strftime("%Y-%m-%d %H:%M")


async def _typing(update: Update):
    """أرسل إشارة Typing لتحسين تجربة المستخدم."""
    try:
        await update.message.chat.send_action(ChatAction.TYPING)
    except Exception:
        pass


def _split_send(text: str, max_len: int = 4000) -> list[str]:
    """تقسيم رسالة طويلة لأجزاء."""
    parts = []
    while len(text) > max_len:
        cut = text[:max_len].rfind("\n")
        if cut == -1:
            cut = max_len
        parts.append(text[:cut])
        text = text[cut:].lstrip()
    parts.append(text)
    return parts


def _fallback(text: str, uid: str) -> dict:
    """صفحة احتياطية فقط عند فشل الذكاء الاصطناعي كلياً."""
    name = f"site-{uid[-4:]}-{int(time.time()) % 100000}"[:30]
    safe = text.replace('"', "'")[:300]
    html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>خطأ مؤقت</title>
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="style.css">
</head>
<body class="bg-slate-950 text-white min-h-screen flex items-center justify-center p-4">
<div class="max-w-md w-full bg-slate-900 border border-red-500/30 rounded-3xl p-8 text-center shadow-2xl">
  <div class="text-5xl mb-4">⚠️</div>
  <h1 class="text-xl font-black mb-3">المحرك مشغول مؤقتاً</h1>
  <p class="text-slate-400 text-sm mb-4">طلبك: <span class="text-yellow-400">{safe}</span></p>
  <p class="text-slate-500 text-xs">أعد إرسال الطلب وسيُنفَّذ كاملاً.</p>
</div>
<script src="script.js"></script>
</body></html>"""
    return {
        "projectName": name,
        "files": [
            {"path": "index.html", "content": html},
            {"path": "style.css",  "content": "body{font-family:'Cairo',sans-serif}"},
            {"path": "script.js",  "content": "// fallback"},
        ]
    }


def _project_keyboard(proj_name: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 افتح الموقع", url=url),
         InlineKeyboardButton("✏️ تعديل", callback_data=f"edit|{proj_name}")],
        [InlineKeyboardButton("📋 نسخ الرابط", callback_data=f"copy|{proj_name}|{url}"),
         InlineKeyboardButton("🗑 حذف", callback_data=f"del|{proj_name}")],
    ])


# ── Commands ──────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.from_user.first_name or "صديقي"
    await update.message.reply_text(
        f"👋 أهلاً {name}!\n\n"
        "أنا بوت بناء المواقع بالذكاء الاصطناعي 🤖\n\n"
        "🔥 ما أقدر أسويه:\n"
        "• مواقع متاجر إلكترونية كاملة\n"
        "• ألعاب تفاعلية في المتصفح\n"
        "• لوحات تحكم ودashboards\n"
        "• أي موقع تتخيله!\n\n"
        "📌 فقط أرسل وصف ما تريد وسأبنيه وأنشره على Vercel فوراً 🚀\n\n"
        "الأوامر:\n"
        "/help — شرح مفصل\n"
        "/my — مشاريعك\n"
        "/stats — إحصائياتك\n"
        "/cancel — إلغاء التعديل"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *دليل الاستخدام*\n\n"
        "*🏗 بناء موقع جديد:*\n"
        "أرسل وصفاً تفصيلياً لما تريد:\n"
        "مثال: _سوّي متجر ملابس بألوان داكنة فيه 3 أقسام وسلة تسوق_\n\n"
        "*✏️ تعديل موقع:*\n"
        "اضغط زر ✏️ تعديل تحت الموقع، ثم أرسل ما تريد تغييره.\n\n"
        "*💡 نصائح للحصول على أفضل نتيجة:*\n"
        "• كن تفصيلياً في الوصف\n"
        "• حدد الألوان والأقسام التي تريدها\n"
        "• ذكر الميزات المهمة (سلة، دفع، تسجيل...)\n\n"
        "*⚙️ الأوامر:*\n"
        "/my — مشاريعك النشطة\n"
        "/stats — إحصائياتك\n"
        "/cancel — إلغاء وضع التعديل",
        parse_mode="Markdown"
    )


async def cmd_my(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    projects = get_projects(uid)
    if not projects:
        await update.message.reply_text(
            "📭 لا توجد مشاريع نشطة.\n\nأرسل وصف موقعك لإنشاء أول مشروع! 🚀"
        )
        return

    await update.message.reply_text(f"📂 *مشاريعك ({len(projects)}):*", parse_mode="Markdown")

    for p in projects:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 افتح", url=p["url"]),
             InlineKeyboardButton("✏️ تعديل", callback_data=f"edit|{p['name']}"),
             InlineKeyboardButton("🗑 حذف", callback_data=f"del|{p['name']}")],
        ])
        await update.message.reply_text(
            f"📛 `{p['name']}`\n🔗 {p['url']}",
            reply_markup=kb,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    s = USER_STATS.get(uid, {"builds": 0, "edits": 0, "last_active": "—"})
    projects = get_projects(uid)
    await update.message.reply_text(
        f"📊 *إحصائياتك:*\n\n"
        f"🏗 مواقع بُنيت: {s['builds']}\n"
        f"✏️ تعديلات: {s['edits']}\n"
        f"📂 مشاريع نشطة: {len(projects)}\n"
        f"🕐 آخر نشاط: {s['last_active']}",
        parse_mode="Markdown"
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    if uid in EDIT_MODE:
        proj = EDIT_MODE.pop(uid)
        await update.message.reply_text(f"❌ تم إلغاء تعديل `{proj}`.", parse_mode="Markdown")
    else:
        await update.message.reply_text("ℹ️ لست في وضع التعديل حالياً.")


# ── Build ──────────────────────────────────────
async def _do_build(update: Update, uid: str, text: str) -> dict | None:
    await _typing(update)
    await update.message.reply_text(
        "⚙️ *جاري بناء موقعك...*\n\n"
        "المحرك الذكي يحلل طلبك ويولد الكود 🧠\n"
        "_(قد يستغرق 15-40 ثانية)_",
        parse_mode="Markdown"
    )
    try:
        log(f"[BUILD] uid={uid} req={text[:100]}")
        raw = builder(text)
        data = safe_parse(raw)
        if not data:
            raise ValueError("safe_parse=None")
        _track(uid, "build")
        log(f"[BUILD_OK] uid={uid} proj={data.get('projectName')}")
        return data
    except RuntimeError as e:
        log(f"[BUILD_FAIL] uid={uid} err={e}")
        await update.message.reply_text(
            "⚠️ المحرك مشغول الآن، جاري رفع صفحة مؤقتة.\n"
            "أعد الطلب بعد لحظة للحصول على الموقع الكامل."
        )
        return _fallback(text, uid)
    except Exception as e:
        log(f"[BUILD_ERR] uid={uid} err={e}")
        await update.message.reply_text("⚠️ خطأ غير متوقع، جاري رفع صفحة مؤقتة.")
        return _fallback(text, uid)


# ── Edit ───────────────────────────────────────
async def _do_edit(update: Update, uid: str, text: str, proj: str) -> dict | None:
    await _typing(update)
    await update.message.reply_text(
        f"🔄 *معالجة التعديلات على* `{proj}`...",
        parse_mode="Markdown"
    )

    local = get_project_files(uid, proj)
    current = ""
    if local:
        for f in local:
            current += f"\n--- {f['path']} ---\n{f['content']}\n"
    else:
        await update.message.reply_text(
            "⚠️ لم أجد الملفات محلياً، سيُعامَل كمشروع جديد.",
        )

    try:
        log(f"[EDIT] uid={uid} proj={proj} req={text[:100]}")
        raw = editor(text, current_code=current)
        data = safe_parse(raw)
        if not data:
            raise ValueError("safe_parse=None")
        data["projectName"] = proj
        _track(uid, "edit")
        log(f"[EDIT_OK] uid={uid} proj={proj}")
        return data
    except RuntimeError as e:
        log(f"[EDIT_FAIL] uid={uid} err={e}")
        await update.message.reply_text(
            "❌ فشل التعديل بعد كل المحاولات.\n"
            "أرسل /cancel ثم أعد المحاولة بوصف أوضح."
        )
        return None
    except Exception as e:
        log(f"[EDIT_ERR] uid={uid} err={e}")
        await update.message.reply_text("❌ خطأ غير متوقع في التعديل.")
        return None


# ── Deploy ─────────────────────────────────────
async def _do_deploy(update: Update, uid: str, data: dict):
    await _typing(update)
    await update.message.reply_text("📦 *رفع الملفات إلى Vercel...*", parse_mode="Markdown")
    try:
        build_project(data, uid)
        url = deploy_project(data["projectName"], data.get("files", []))
        add_project(uid, data["projectName"], url)
        log(f"[DEPLOY_OK] uid={uid} proj={data['projectName']} url={url}")

        await update.message.reply_text(
            f"✅ *موقعك جاهز!*\n\n"
            f"📛 الاسم: `{data['projectName']}`\n"
            f"🔗 {url}\n\n"
            f"استخدم الأزرار للتحكم بموقعك 👇",
            reply_markup=_project_keyboard(data["projectName"], url),
            parse_mode="Markdown"
        )
    except Exception as e:
        log(f"[DEPLOY_ERR] uid={uid} err={e}")
        await update.message.reply_text(
            "❌ *فشل الرفع إلى Vercel*\n\n"
            "الأسباب المحتملة:\n"
            "• VERCEL_TOKEN منتهي أو خاطئ\n"
            "• تجاوزت حد المشاريع المجانية (100)\n"
            "• مشكلة في الاتصال",
            parse_mode="Markdown"
        )


# ── Main message handler ───────────────────────
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = str(update.message.from_user.id)
    text = update.message.text.strip()

    if not text:
        await update.message.reply_text("⚠️ الرسالة فارغة، أرسل وصف موقعك.")
        return

    allowed, remaining = _allow(uid)
    if not allowed:
        await update.message.reply_text(f"⏳ انتظر {remaining} ثانية بين الطلبات.")
        return

    # وضع التعديل
    if uid in EDIT_MODE:
        proj = EDIT_MODE.pop(uid)
        data = await _do_edit(update, uid, text, proj)
    else:
        data = await _do_build(update, uid, text)

    if not data:
        return

    await _do_deploy(update, uid, data)


# ── Callback buttons ───────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = str(q.from_user.id)

    if "|" not in q.data:
        return

    parts  = q.data.split("|")
    action = parts[0]
    proj   = parts[1]

    if action == "edit":
        EDIT_MODE[uid] = proj
        await q.message.reply_text(
            f"✏️ *وضع تعديل:* `{proj}`\n\n"
            f"أرسل الآن التغييرات التي تريدها بالتفصيل.\n"
            f"للإلغاء: /cancel",
            parse_mode="Markdown"
        )

    elif action == "del":
        # زر تأكيد الحذف
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ نعم، احذف", callback_data=f"confirm_del|{proj}"),
             InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_del|{proj}")],
        ])
        await q.message.reply_text(
            f"⚠️ *هل أنت متأكد من حذف* `{proj}`؟\n\nلا يمكن التراجع عن هذا الإجراء.",
            reply_markup=kb,
            parse_mode="Markdown"
        )

    elif action == "confirm_del":
        await q.message.reply_text(f"🗑 جاري حذف `{proj}`...", parse_mode="Markdown")
        try:
            delete_vercel_project(proj)
        except Exception as e:
            log(f"[DEL_VERCEL_ERR] proj={proj} err={e}")
        delete_project_files(uid, proj)
        delete_project(uid, proj)
        await q.message.reply_text(f"✅ تم حذف `{proj}` بنجاح.", parse_mode="Markdown")

    elif action == "cancel_del":
        await q.message.reply_text("↩️ تم إلغاء الحذف.")

    elif action == "copy":
        url = parts[2] if len(parts) > 2 else ""
        await q.message.reply_text(
            f"📋 رابط `{proj}`:\n\n`{url}`",
            parse_mode="Markdown"
        )


# ── Entry point ────────────────────────────────
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start",  cmd_start))
app.add_handler(CommandHandler("help",   cmd_help))
app.add_handler(CommandHandler("my",     cmd_my))
app.add_handler(CommandHandler("stats",  cmd_stats))
app.add_handler(CommandHandler("cancel", cmd_cancel))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
app.add_handler(CallbackQueryHandler(handle_callback))

if __name__ == "__main__":
    log("✅ البوت يعمل — النسخة المطورة")
    app.run_polling()

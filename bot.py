"""
bot.py — Telegram bot — يحفظ المشاريع بشكل دائم في قاعدة بيانات.
"""
import os
import time
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
from store import add_project, get_projects, delete_project, get_project_files_db
from file_manager import delete_project_files, get_project_files
from logger import log

BOT_TOKEN = os.getenv("BOT_TOKEN")

_cooldown: dict  = {}
EDIT_MODE: dict  = {}
USER_STATS: dict = {}


# ── Helpers ───────────────────────────────────
def _allow(uid: str, seconds: int = 8):
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
    try:
        await update.message.chat.send_action(ChatAction.TYPING)
    except Exception:
        pass


def _fallback(text: str, uid: str) -> dict:
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
        [InlineKeyboardButton("🗑 حذف", callback_data=f"del|{proj_name}")],
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
        "📌 فقط أرسل وصف ما تريد وسأبنيه وأنشره فوراً 🚀\n\n"
        "الأوامر:\n"
        "/help — شرح مفصل\n"
        "/my — مشاريعك\n"
        "/stats — إحصائياتك\n"
        "/cancel — إلغاء التعديل"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 دليل الاستخدام\n\n"
        "🏗 بناء موقع جديد:\n"
        "أرسل وصفاً تفصيلياً لما تريد.\n"
        "مثال: سوّي متجر ملابس بألوان داكنة فيه 3 أقسام وسلة تسوق\n\n"
        "✏️ تعديل موقع:\n"
        "اضغط زر تعديل تحت الموقع، ثم أرسل ما تريد تغييره.\n\n"
        "💡 نصائح:\n"
        "• كن تفصيلياً في الوصف\n"
        "• حدد الألوان والأقسام\n"
        "• اذكر الميزات المهمة (سلة، دفع، تسجيل...)\n\n"
        "⚙️ الأوامر:\n"
        "/my — مشاريعك النشطة\n"
        "/stats — إحصائياتك\n"
        "/cancel — إلغاء وضع التعديل"
    )


async def cmd_my(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    projects = get_projects(uid)
    if not projects:
        await update.message.reply_text("📭 لا توجد مشاريع نشطة.\n\nأرسل وصف موقعك لإنشاء أول مشروع! 🚀")
        return

    await update.message.reply_text(f"📂 مشاريعك ({len(projects)}):")
    for p in projects:
        await update.message.reply_text(
            f"📛 {p['name']}\n🔗 {p['url']}",
            reply_markup=_project_keyboard(p["name"], p["url"]),
            disable_web_page_preview=True
        )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    s = USER_STATS.get(uid, {"builds": 0, "edits": 0, "last_active": "—"})
    projects = get_projects(uid)
    await update.message.reply_text(
        f"📊 إحصائياتك:\n\n"
        f"🏗 مواقع بُنيت: {s['builds']}\n"
        f"✏️ تعديلات: {s['edits']}\n"
        f"📂 مشاريع نشطة: {len(projects)}\n"
        f"🕐 آخر نشاط: {s['last_active']}"
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    if uid in EDIT_MODE:
        proj = EDIT_MODE.pop(uid)
        await update.message.reply_text(f"❌ تم إلغاء تعديل {proj}.")
    else:
        await update.message.reply_text("ℹ️ لست في وضع التعديل حالياً.")


# ── Build ──────────────────────────────────────
async def _do_build(update: Update, uid: str, text: str):
    await _typing(update)
    await update.message.reply_text(
        "⚙️ جاري بناء موقعك...\n"
        "المحرك الذكي يحلل طلبك ويولد الكود 🧠"
    )
    try:
        log(f"[BUILD] uid={uid} req={text[:100]}")
        data = safe_parse(builder(text))
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
async def _do_edit(update: Update, uid: str, text: str, proj: str):
    await _typing(update)
    await update.message.reply_text(f"🔄 معالجة التعديلات على {proj}...")

    # أولاً جرّب من القرص، وإلا من قاعدة البيانات
    local = get_project_files(uid, proj)
    if not local:
        local = get_project_files_db(uid, proj)

    current = ""
    if local:
        for f in local:
            current += f"\n--- {f['path']} ---\n{f['content']}\n"
    else:
        await update.message.reply_text("⚠️ لم أجد الملفات، سيُعامَل كمشروع جديد.")

    try:
        log(f"[EDIT] uid={uid} proj={proj} req={text[:100]}")
        data = safe_parse(editor(text, current_code=current))
        if not data:
            raise ValueError("safe_parse=None")
        data["projectName"] = proj
        _track(uid, "edit")
        log(f"[EDIT_OK] uid={uid} proj={proj}")
        return data
    except RuntimeError as e:
        log(f"[EDIT_FAIL] uid={uid} err={e}")
        await update.message.reply_text("❌ فشل التعديل بعد كل المحاولات.\nأرسل /cancel ثم أعد المحاولة.")
        return None
    except Exception as e:
        log(f"[EDIT_ERR] uid={uid} err={e}")
        await update.message.reply_text("❌ خطأ غير متوقع في التعديل.")
        return None


# ── Deploy ─────────────────────────────────────
async def _do_deploy(update: Update, uid: str, data: dict):
    await _typing(update)
    await update.message.reply_text("📦 رفع الملفات...")
    try:
        build_project(data, uid)
        url = deploy_project(data["projectName"], data.get("files", []))
        # حفظ دائم في قاعدة البيانات (يشمل محتوى الملفات لاسترجاعها بعد إعادة التشغيل)
        add_project(uid, data["projectName"], url, data.get("files", []))
        log(f"[DEPLOY_OK] uid={uid} proj={data['projectName']} url={url}")

        await update.message.reply_text(
            f"✅ موقعك جاهز!\n\n"
            f"📛 الاسم: {data['projectName']}\n"
            f"🔗 {url}\n\n"
            f"استخدم الأزرار للتحكم بموقعك 👇",
            reply_markup=_project_keyboard(data["projectName"], url),
        )
    except Exception as e:
        log(f"[DEPLOY_ERR] uid={uid} err={e}")
        await update.message.reply_text("❌ فشل الرفع. تحقق من إعدادات السيرفر.")


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
            f"✏️ وضع تعديل: {proj}\n\n"
            f"أرسل الآن التغييرات التي تريدها بالتفصيل.\n"
            f"للإلغاء: /cancel"
        )

    elif action == "del":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ نعم، احذف", callback_data=f"confirm_del|{proj}"),
             InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_del|{proj}")],
        ])
        await q.message.reply_text(
            f"⚠️ هل أنت متأكد من حذف {proj}؟\n\nلا يمكن التراجع عن هذا الإجراء.",
            reply_markup=kb
        )

    elif action == "confirm_del":
        await q.message.reply_text(f"🗑 جاري حذف {proj}...")
        try:
            delete_vercel_project(proj)
        except Exception as e:
            log(f"[DEL_LOCAL_ERR] proj={proj} err={e}")
        delete_project_files(uid, proj)
        delete_project(uid, proj)  # يحذف من قاعدة البيانات أيضاً
        await q.message.reply_text(f"✅ تم حذف {proj} بنجاح.")

    elif action == "cancel_del":
        await q.message.reply_text("↩️ تم إلغاء الحذف.")


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

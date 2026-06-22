"""
bot.py — Telegram bot — يحفظ المشاريع بشكل دائم في قاعدة بيانات.
مضمون الرد دائماً على أي صورة أو رسالة (try/except شامل في كل هاندلر).
"""
import os
import time
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler, ContextTypes,
    filters, CallbackQueryHandler, CommandHandler
)
from telegram.constants import ChatAction

from ai import builder, editor, plan_chat, build_from_conversation
from builder import build_project
from deploy import deploy_project, delete_vercel_project, remove_background
from validator import safe_parse
from store import add_project, get_projects, delete_project, get_project_files_db, rename_project
from file_manager import delete_project_files, get_project_files
from logger import log

BOT_TOKEN = os.getenv("BOT_TOKEN")

_cooldown: dict  = {}
EDIT_MODE: dict  = {}
USER_STATS: dict = {}
PENDING_IMAGE: dict = {}
PENDING_BUILD: dict = {}  # uid -> {"data": dict, "is_edit": bool, "proj": str|None}
PLANNING: dict = {}       # uid -> [{"role": "user"/"assistant", "content": "..."}] محادثة تخطيط قبل البناء
LAST_VERSION: dict = {}   # proj_name -> {"files": [...], "url": str} — نسخة سابقة واحدة لكل مشروع (للرجوع/undo)
RENAME_MODE: dict = {}    # uid -> proj_name — بانتظار إرسال الاسم الجديد التعريفي

SITES_DIR = os.path.join(os.path.dirname(__file__), "sites")
UPLOADS_DIR = os.path.join(SITES_DIR, "_uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

# نفس متغير BASE_URL المستخدم في deploy.py — لازم يكون مضبوط بـ Render
PUBLIC_BASE = os.getenv("BASE_URL", "").rstrip("/")


def _allow(uid: str, seconds: int = 8):
    now = time.time()
    if now - _cooldown.get(uid, 0) < seconds:
        remaining = int(seconds - (now - _cooldown.get(uid, 0)))
        return False, remaining
    _cooldown[uid] = now
    return True, 0


def _track(uid: str, action: str):
    s = USER_STATS.setdefault(uid, {"builds": 0, "edits": 0, "images": 0, "last_active": ""})
    if action in s:
        s[action] += 1
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
        [InlineKeyboardButton("📝 تعديل الاسم", callback_data=f"rename|{proj_name}"),
         InlineKeyboardButton("🗑 حذف", callback_data=f"del|{proj_name}")],
    ])


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.from_user.first_name or "صديقي"
    await update.message.reply_text(
        f"👋 أهلاً {name}!\n\n"
        "أنا بوت بناء المواقع بالذكاء الاصطناعي 🤖\n\n"
        "📌 احكِ لي عن فكرتك بشكل طبيعي، وأنا أرد وأسأل عن أي تفصيل ناقص.\n"
        "✅ لما تكون جاهز (تقول مثلاً: يلا ابدأ)، أبني الموقع فعلياً وأعرض لك معاينة حقيقية قبل النشر.\n"
        "🔎 لو طلبت روابط حقيقية (فيديوهات، مواقع)، أبحث فعلياً بالإنترنت وأضمّنها بالموقع.\n"
        "📷 تقدر ترسل صورة (لوقو/منتج) مع وصفها في أي وقت.\n\n"
        "/help — شرح مفصل\n/my — مشاريعك\n/stats — إحصائياتك\n/cancel — إلغاء أي محادثة جارية"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 دليل الاستخدام\n\n"
        "🏗 بناء موقع جديد: احكِ لي عن فكرتك بشكل طبيعي، حتى لو على دفعات.\n"
        "أنا أرد عليك وأسألك عن أي تفصيل ناقص، ولا أبدأ البناء إلا لما أحس إنك جاهز "
        "(مثل ما تقول: يلا ابدأ / سويها / تمام جاهز).\n"
        "كل ما تقوله يُلتزم به بالضبط — لا أخترع أقسام أو منتجات من عندي.\n\n"
        "👀 بعد البناء تشوف معاينة فعلية قبل النشر النهائي، وتقدر تطلب تعديلات عليها قبل تأكيد النشر.\n\n"
        "✏️ تعديل موقع منشور: اضغط زر تعديل، ثم أرسل نص أو صورة (مع وصف أو بدونه).\n\n"
        "📷 صورة بدون نص: نسألك وصف الاستخدام بعدها.\n"
        "📷 صورة مع نص: نطبّق التعديل فوراً.\n\n"
        "/my — مشاريعك\n/stats — إحصائياتك\n/cancel — إلغاء أي محادثة أو تعديل جارٍ"
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
            f"📛 {p['display_name']}\n🔗 {p['url']}",
            reply_markup=_project_keyboard(p["name"], p["url"]),
            disable_web_page_preview=True
        )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    s = USER_STATS.get(uid, {"builds": 0, "edits": 0, "images": 0, "last_active": "—"})
    projects = get_projects(uid)
    await update.message.reply_text(
        f"📊 إحصائياتك:\n\n🏗 مواقع: {s['builds']}\n✏️ تعديلات: {s['edits']}\n"
        f"📷 صور: {s.get('images', 0)}\n📂 نشطة: {len(projects)}\n🕐 آخر نشاط: {s['last_active']}"
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    PENDING_IMAGE.pop(uid, None)
    PENDING_BUILD.pop(uid, None)
    PLANNING.pop(uid, None)
    if uid in RENAME_MODE:
        RENAME_MODE.pop(uid)
        await update.message.reply_text("❌ تم إلغاء تعديل الاسم.")
        return
    if uid in EDIT_MODE:
        proj = EDIT_MODE.pop(uid)
        await update.message.reply_text(f"❌ تم إلغاء تعديل {proj}.")
    else:
        await update.message.reply_text("ℹ️ لست في وضع التعديل حالياً.")


async def _do_build(update: Update, uid: str, text: str):
    await _typing(update)
    await update.message.reply_text("⚙️ جاري بناء موقعك...\nالمحرك الذكي يحلل طلبك 🧠")
    try:
        log(f"[BUILD] uid={uid} req={text[:100]}")
        data = safe_parse(builder(text))
        if not data:
            raise ValueError("safe_parse=None")
        _track(uid, "builds")
        log(f"[BUILD_OK] uid={uid} proj={data.get('projectName')}")
        return data
    except RuntimeError as e:
        log(f"[BUILD_FAIL] uid={uid} err={e}")
        await update.message.reply_text("⚠️ المحرك مشغول الآن، جاري رفع صفحة مؤقتة.\nأعد الطلب بعد لحظة.")
        return _fallback(text, uid)
    except Exception as e:
        log(f"[BUILD_ERR] uid={uid} err={e}")
        await update.message.reply_text("⚠️ خطأ غير متوقع، جاري رفع صفحة مؤقتة.")
        return _fallback(text, uid)


async def _do_build_from_conversation(update: Update, uid: str, conversation: list):
    """يبني الموقع من كامل محادثة التخطيط — يضمن التزام AI بكل تفصيلة ذكرها المستخدم فقط."""
    await _typing(update)
    await update.message.reply_text("⚙️ تمام، جاري بناء موقعك بناءً على كل ما اتفقنا عليه 🧠")
    user_msgs = " ".join(m["content"] for m in conversation if m["role"] == "user")
    try:
        log(f"[BUILD_CONV] uid={uid} turns={len(conversation)}")
        data = safe_parse(build_from_conversation(conversation))
        if not data:
            raise ValueError("safe_parse=None")
        _track(uid, "builds")
        log(f"[BUILD_CONV_OK] uid={uid} proj={data.get('projectName')}")
        return data
    except RuntimeError as e:
        log(f"[BUILD_CONV_FAIL] uid={uid} err={e}")
        await update.message.reply_text("⚠️ المحرك مشغول الآن، جاري رفع صفحة مؤقتة.\nأعد الطلب بعد لحظة.")
        return _fallback(user_msgs, uid)
    except Exception as e:
        log(f"[BUILD_CONV_ERR] uid={uid} err={e}")
        await update.message.reply_text("⚠️ خطأ غير متوقع، جاري رفع صفحة مؤقتة.")
        return _fallback(user_msgs, uid)


async def _do_edit(update: Update, uid: str, text: str, proj: str,
                    image_url: Optional[str] = None, image_path: Optional[str] = None):
    await _typing(update)
    await update.message.reply_text(f"🔄 معالجة التعديلات على {proj}...")

    local = get_project_files(uid, proj) or get_project_files_db(uid, proj)
    current = ""
    if local:
        for f in local:
            current += f"\n--- {f['path']} ---\n{f['content']}\n"
        # نحفظ نسخة الموقع الحالية قبل التعديل — تُستخدم بزر "↩️ رجوع" لو ما عجب التعديل الجديد
        LAST_VERSION[proj] = {"files": local}
    else:
        await update.message.reply_text("⚠️ لم أجد الملفات، سيُعامَل كمشروع جديد.")

    try:
        log(f"[EDIT] uid={uid} proj={proj} req={text[:100]} img={'yes' if image_url else 'no'}")
        data = safe_parse(editor(text, current_code=current, image_url=image_url, image_path=image_path))
        if not data:
            raise ValueError("safe_parse=None")
        data["projectName"] = proj
        _track(uid, "edits")
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


async def _do_preview(update: Update, uid: str, data: dict, is_edit: bool, original_proj: Optional[str] = None):
    """
    ينشر الموقع تحت اسم معاينة مؤقت ويعرضه فعلياً قابل للفتح، بدل النشر المباشر بالاسم النهائي.
    يخزن الـ data بانتظار قرار المستخدم: نشر نهائي (يثبّت بالاسم الحقيقي) أو تعديل (يرجع لوضع التعديل).
    """
    await _typing(update)
    await update.message.reply_text("📦 جاري تحضير معاينة موقعك...")
    try:
        preview_name = data["projectName"] if is_edit else f"preview-{data['projectName']}-{int(time.time()) % 10000}"
        preview_data = {**data, "projectName": preview_name}

        build_project(preview_data, uid)
        preview_url = deploy_project(preview_name, preview_data.get("files", []))

        PENDING_BUILD[uid] = {
            "data": data,
            "is_edit": is_edit,
            "proj": original_proj,
            "preview_name": preview_name,
        }

        buttons = [
            [InlineKeyboardButton("🌐 افتح المعاينة", url=preview_url)],
            [InlineKeyboardButton("✅ نشر الموقع", callback_data="confirm_publish"),
             InlineKeyboardButton("✏️ تعديل أكثر", callback_data="continue_edit")],
        ]
        # زر الرجوع يظهر فقط لو فيه نسخة سابقة محفوظة لهذا المشروع بالذات (يعني هذا تعديل، مو بناء أول مرة)
        if original_proj and original_proj in LAST_VERSION:
            buttons.append([InlineKeyboardButton("↩️ رجوع للنسخة السابقة", callback_data="undo_edit")])

        kb = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(
            f"👀 هذي معاينة موقعك — افتحها وشوفها قبل ما تقرر:\n🔗 {preview_url}\n\n"
            f"إذا عجبتك اضغط «نشر الموقع»، أو «تعديل أكثر» لمواصلة التحسين"
            + (" أو «رجوع» لاسترجاع النسخة قبل هذا التعديل." if original_proj and original_proj in LAST_VERSION else "."),
            reply_markup=kb,
        )
    except Exception as e:
        log(f"[PREVIEW_ERR] uid={uid} err={e}")
        await update.message.reply_text("❌ فشل تحضير المعاينة. تحقق من إعدادات السيرفر (BASE_URL).")


async def _do_deploy(update: Update, uid: str, data: dict):
    """نشر نهائي مباشر بالاسم الحقيقي (يُستخدم بعد تأكيد المعاينة، أو يفضل استخدام _do_preview قبله)."""
    await _typing(update)
    await update.message.reply_text("📦 رفع الملفات...")
    try:
        build_project(data, uid)
        url = deploy_project(data["projectName"], data.get("files", []))
        add_project(uid, data["projectName"], url, data.get("files", []))
        log(f"[DEPLOY_OK] uid={uid} proj={data['projectName']} url={url}")
        await update.message.reply_text(
            f"✅ موقعك جاهز!\n\n📛 الاسم: {data['projectName']}\n🔗 {url}\n\nاستخدم الأزرار 👇",
            reply_markup=_project_keyboard(data["projectName"], url),
        )
    except Exception as e:
        log(f"[DEPLOY_ERR] uid={uid} err={e}")
        await update.message.reply_text("❌ فشل الرفع. تحقق من إعدادات السيرفر (BASE_URL).")


async def _save_photo(update: Update, uid: str) -> Optional[dict]:
    try:
        photo = update.message.photo[-1]
        tg_file = await photo.get_file()
        filename = f"{uid}_{int(time.time())}.jpg"
        local_path = os.path.join(UPLOADS_DIR, filename)
        await tg_file.download_to_drive(local_path)

        if not PUBLIC_BASE:
            log(f"[IMG_WARN] uid={uid} BASE_URL غير مضبوط")
            return {"path": local_path, "url": ""}

        url = f"{PUBLIC_BASE}/s/_uploads/{filename}"
        log(f"[IMG_OK] uid={uid} url={url}")
        return {"path": local_path, "url": url}
    except Exception as e:
        log(f"[IMG_ERR] uid={uid} err={e}")
        return None


class _FakeUpdate:
    """غلاف بسيط يجعل CallbackQuery.message يبدو كـ Update.message للدوال التي تتوقع update.message.reply_text."""
    def __init__(self, message):
        self.message = message


async def _continue_photo_flow(update, uid: str, saved: dict, caption: str):
    """
    يكمل معالجة الصورة بعد تحديد قرار إزالة الخلفية (سواء طُبّقت أو تم تجاوزها).
    update: يجب أن يحتوي .message.reply_text (Update عادي، أو _FakeUpdate من CallbackQuery).
    """
    if uid in EDIT_MODE:
        if caption:
            proj = EDIT_MODE.pop(uid)
            _track(uid, "images")
            data = await _do_edit(update, uid, caption, proj, image_url=saved["url"], image_path=saved["path"])
            if data:
                await _do_preview(update, uid, data, is_edit=True, original_proj=proj)
        else:
            PENDING_IMAGE[uid] = saved
            await update.message.reply_text(
                "📸 تمام. أرسل الآن وصف كيف تريد استخدامها:\n"
                "مثلاً: خلي اللوقو هذي الصورة / هذا المنتج حط له هذي الصورة."
            )
        return

    if not caption:
        await update.message.reply_text(
            "📸 تمام. أرسل وصفاً يوضح فكرة الموقع المطلوب "
            "(مثلاً: سوّي متجر إلكترونيات وخلي هذي الصورة اللوقو)."
        )
        PENDING_IMAGE[uid] = saved
        return

    history = PLANNING.setdefault(uid, [])
    history.append({"role": "user", "content": f"{caption} [صورة مرفقة: {saved['url']}]"})

    try:
        reply_text, ready = plan_chat(history)
    except RuntimeError as e:
        log(f"[PLAN_CHAT_PHOTO_FAIL] uid={uid} err={e}")
        await update.message.reply_text("⚠️ المحرك مشغول الآن، حاول إعادة الإرسال بعد لحظة.")
        return

    history.append({"role": "assistant", "content": reply_text})

    if not ready:
        await update.message.reply_text(reply_text)
        return

    await update.message.reply_text(reply_text)
    data = await _do_build_from_conversation(update, uid, history)
    PLANNING.pop(uid, None)
    PENDING_IMAGE.pop(uid, None)

    if data:
        await _do_preview(update, uid, data, is_edit=False, original_proj=None)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مضمون يرد دائماً — أي خطأ غير متوقع يُمسك في try/except خارجي شامل."""
    uid = str(update.message.from_user.id)
    try:
        await _typing(update)
        saved = await _save_photo(update, uid)

        if not saved:
            await update.message.reply_text("⚠️ حدث خطأ أثناء حفظ الصورة. حاول مرة أخرى.")
            return

        if not saved["url"]:
            await update.message.reply_text(
                "⚠️ تعذّر توليد رابط عام للصورة لأن BASE_URL غير مضبوط بالسيرفر.\n"
                "أضف متغير BASE_URL في Render Environment Variables بقيمة رابط موقعك (https://...)."
            )
            return

        caption = (update.message.caption or "").strip()
        saved["caption"] = caption
        PENDING_IMAGE[uid] = saved

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🪄 إزالة الخلفية", callback_data="rmbg_yes"),
             InlineKeyboardButton("➡️ تجاوز", callback_data="rmbg_no")],
        ])
        await update.message.reply_text(
            "📸 استلمت الصورة. تبي أزيل الخلفية منها قبل الاستخدام؟",
            reply_markup=kb,
        )

    except Exception as e:
        log(f"[PHOTO_HANDLER_FATAL] uid={uid} err={e}")
        try:
            await update.message.reply_text("❌ حدث خطأ غير متوقع أثناء معالجة الصورة. حاول مرة أخرى أو أرسل /cancel.")
        except Exception:
            pass


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    try:
        text = (update.message.text or "").strip()
        if not text:
            await update.message.reply_text("⚠️ الرسالة فارغة، أرسل وصف موقعك.")
            return

        allowed, remaining = _allow(uid)
        if not allowed:
            await update.message.reply_text(f"⏳ انتظر {remaining} ثانية بين الطلبات.")
            return

        if uid in EDIT_MODE:
            proj = EDIT_MODE.pop(uid)
            pending = PENDING_IMAGE.pop(uid, None)
            if pending:
                _track(uid, "images")
                data = await _do_edit(update, uid, text, proj, image_url=pending["url"], image_path=pending["path"])
            else:
                data = await _do_edit(update, uid, text, proj)
            if not data:
                return
            await _do_preview(update, uid, data, is_edit=True, original_proj=proj)
            return

        # ── محادثة تخطيط قبل البناء ──────────────
        # نتراكم رسائل المستخدم بهذا السياق إلى أن يقرر AI نفسه إنه فهم وجاهز للبناء
        history = PLANNING.setdefault(uid, [])

        pending_img = PENDING_IMAGE.pop(uid, None)
        if pending_img:
            history.append({"role": "user", "content": f"{text} [صورة مرفقة: {pending_img['url']}]"})
            _track(uid, "images")
        else:
            history.append({"role": "user", "content": text})

        await _typing(update)
        try:
            reply_text, ready = plan_chat(history)
        except RuntimeError as e:
            log(f"[PLAN_CHAT_FAIL] uid={uid} err={e}")
            await update.message.reply_text("⚠️ المحرك مشغول الآن، حاول إعادة كتابة طلبك بعد لحظة.")
            return

        history.append({"role": "assistant", "content": reply_text})

        if not ready:
            await update.message.reply_text(reply_text)
            return

        # المستخدم جاهز — نبني فعلياً من كامل المحادثة المتراكمة
        await update.message.reply_text(reply_text)
        data = await _do_build_from_conversation(update, uid, history)
        PLANNING.pop(uid, None)

        if not data:
            return

        await _do_preview(update, uid, data, is_edit=False, original_proj=None)

    except Exception as e:
        log(f"[HANDLE_FATAL] uid={uid} err={e}")
        try:
            await update.message.reply_text("❌ حدث خطأ غير متوقع. حاول مرة أخرى أو أرسل /cancel.")
        except Exception:
            pass


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = str(q.from_user.id)

    # ── أزرار المعاينة (بلا |) ──────────────────
    if q.data == "confirm_publish":
        pending = PENDING_BUILD.pop(uid, None)
        if not pending:
            await q.message.reply_text("⚠️ لا توجد معاينة بانتظار النشر. أرسل طلب جديد.")
            return
        try:
            data = pending["data"]
            build_project(data, uid)
            url = deploy_project(data["projectName"], data.get("files", []))
            add_project(uid, data["projectName"], url, data.get("files", []))
            log(f"[PUBLISH_OK] uid={uid} proj={data['projectName']} url={url}")
            await q.message.reply_text(
                f"✅ تم النشر النهائي!\n\n📛 الاسم: {data['projectName']}\n🔗 {url}\n\nاستخدم الأزرار 👇",
                reply_markup=_project_keyboard(data["projectName"], url),
            )
        except Exception as e:
            log(f"[PUBLISH_ERR] uid={uid} err={e}")
            await q.message.reply_text("❌ فشل النشر النهائي. حاول مرة أخرى.")
        return

    if q.data in ("rmbg_yes", "rmbg_no"):
        saved = PENDING_IMAGE.get(uid)
        if not saved:
            await q.message.reply_text("⚠️ لم أجد الصورة، أرسلها مرة أخرى.")
            return

        caption = saved.get("caption", "")

        if q.data == "rmbg_yes":
            await q.message.reply_text("🪄 جاري إزالة الخلفية...")
            try:
                with open(saved["path"], "rb") as f:
                    raw = f.read()
                processed = remove_background(raw)
                # نحفظ النسخة المعدّلة فوق نفس الملف (PNG شفاف) ونحدّث الرابط بامتداد جديد
                new_filename = os.path.basename(saved["path"]).rsplit(".", 1)[0] + "_nobg.png"
                new_path = os.path.join(UPLOADS_DIR, new_filename)
                with open(new_path, "wb") as f:
                    f.write(processed)
                saved["path"] = new_path
                saved["url"] = f"{PUBLIC_BASE}/s/_uploads/{new_filename}" if PUBLIC_BASE else saved["url"]
                log(f"[RMBG_APPLIED] uid={uid} file={new_filename}")
                await q.message.reply_text("✅ تمت إزالة الخلفية بنجاح.")
            except Exception as e:
                log(f"[RMBG_CALLBACK_ERR] uid={uid} err={e}")
                await q.message.reply_text("⚠️ تعذّرت إزالة الخلفية، سنستخدم الصورة الأصلية.")
        else:
            await q.message.reply_text("➡️ تم تجاوز إزالة الخلفية.")

        await _continue_photo_flow(_FakeUpdate(q.message), uid, saved, caption)
        return

    if q.data == "continue_edit":
        pending = PENDING_BUILD.get(uid)
        if not pending:
            await q.message.reply_text("⚠️ لا توجد معاينة حالية للتعديل عليها. أرسل طلب جديد.")
            return
        # نفتح وضع تعديل على نفس مشروع المعاينة المؤقت (preview_name) — التعديل القادم يبني فوقه
        EDIT_MODE[uid] = pending["preview_name"]
        await q.message.reply_text(
            "✏️ تمام، أرسل الآن التغييرات التي تريدها على المعاينة.\n"
            "بعد التعديل سأعرض لك معاينة جديدة قبل النشر."
        )
        return

    if q.data == "undo_edit":
        pending = PENDING_BUILD.get(uid)
        if not pending or not pending.get("proj"):
            await q.message.reply_text("⚠️ لا توجد نسخة سابقة محفوظة بهذه اللحظة.")
            return

        original_proj = pending["proj"]
        backup = LAST_VERSION.get(original_proj)
        if not backup:
            await q.message.reply_text("⚠️ لا توجد نسخة سابقة محفوظة لهذا المشروع.")
            return

        await q.message.reply_text(f"↩️ جاري استرجاع النسخة السابقة من {original_proj}...")
        try:
            restore_data = {"projectName": original_proj, "files": backup["files"]}
            build_project(restore_data, uid)
            url = deploy_project(original_proj, backup["files"])
            add_project(uid, original_proj, url, backup["files"])
            LAST_VERSION.pop(original_proj, None)
            PENDING_BUILD.pop(uid, None)
            log(f"[UNDO_OK] uid={uid} proj={original_proj}")
            await q.message.reply_text(
                f"✅ تم استرجاع النسخة السابقة بنجاح!\n\n📛 {original_proj}\n🔗 {url}",
                reply_markup=_project_keyboard(original_proj, url),
            )
        except Exception as e:
            log(f"[UNDO_ERR] uid={uid} proj={original_proj} err={e}")
            await q.message.reply_text("❌ فشل استرجاع النسخة السابقة.")
        return

    if "|" not in q.data:
        return

    parts  = q.data.split("|")
    action = parts[0]
    proj   = parts[1]

    if action == "edit":
        EDIT_MODE[uid] = proj
        await q.message.reply_text(
            f"✏️ وضع تعديل: {proj}\n\nأرسل التغييرات بالتفصيل، أو صورة (مع وصف أو بدونه).\nللإلغاء: /cancel"
        )
    elif action == "rename":
        RENAME_MODE[uid] = proj
        await q.message.reply_text(
            "📝 أرسل الآن الاسم الجديد اللي تبيه يظهر بقائمة /my.\n"
            "ملاحظة: هذا لا يغيّر رابط الموقع، فقط الاسم اللي تشوفه عندك.\nللإلغاء: /cancel"
        )
    elif action == "del":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ نعم، احذف", callback_data=f"confirm_del|{proj}"),
             InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_del|{proj}")],
        ])
        await q.message.reply_text(f"⚠️ هل أنت متأكد من حذف {proj}؟", reply_markup=kb)
    elif action == "confirm_del":
        await q.message.reply_text(f"🗑 جاري حذف {proj}...")
        try:
            delete_vercel_project(proj)
        except Exception as e:
            log(f"[DEL_LOCAL_ERR] proj={proj} err={e}")
        delete_project_files(uid, proj)
        delete_project(uid, proj)
        await q.message.reply_text(f"✅ تم حذف {proj} بنجاح.")
    elif action == "cancel_del":
        await q.message.reply_text("↩️ تم إلغاء الحذف.")


app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start",  cmd_start))
app.add_handler(CommandHandler("help",   cmd_help))
app.add_handler(CommandHandler("my",     cmd_my))
app.add_handler(CommandHandler("stats",  cmd_stats))
app.add_handler(CommandHandler("cancel", cmd_cancel))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
app.add_handler(CallbackQueryHandler(handle_callback))

if __name__ == "__main__":
    log("✅ البوت يعمل — النسخة المطورة")
    app.run_polling()

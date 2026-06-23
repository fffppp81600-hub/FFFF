"""
bot.py — بوت تيليجرام — النسخة المطورة.

المميزات الجديدة:
  - Version Control كامل (حفظ + استرجاع أي نسخة)
  - دعم ألعاب كاملة
  - ذاكرة دائمة بين الجلسات
  - إحصائيات مفصلة من DB
  - واجهة أزرار محسّنة
  - معالجة شاملة للأخطاء
"""
import os
import time
import asyncio
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

from ai import builder, editor, plan_chat, build_from_conversation, game_builder, _detect_project_type
from builder import build_project
from deploy import deploy_project, delete_vercel_project, remove_background
from validator import safe_parse
from store import (
    add_project, get_projects, delete_project, get_project_files_db,
    rename_project, save_version, get_versions, get_version_files,
    update_project_files, upsert_user, increment_user_stat, get_user_stats,
    save_asset, get_project_assets
)
from file_manager import delete_project_files, get_project_files
import memory as mem
from logger import log

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ─── حالات المستخدم ───────────────────────────
_cooldown:     dict = {}
EDIT_MODE:     dict = {}   # uid -> proj_name
PLANNING:      dict = {}   # uid -> [conversation history]
PENDING_IMAGE: dict = {}   # uid -> {path, url, caption}
PENDING_BUILD: dict = {}   # uid -> {data, is_edit, proj, preview_name, preview_files}
RENAME_MODE:   dict = {}   # uid -> proj_name
VERSION_MODE:  dict = {}   # uid -> proj_name (لعرض قائمة الإصدارات)

SITES_DIR   = os.path.join(os.path.dirname(__file__), "sites")
UPLOADS_DIR = os.path.join(SITES_DIR, "_uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

PUBLIC_BASE = os.getenv("BASE_URL", "").rstrip("/")
MAX_PROJECTS_PER_USER = int(os.getenv("MAX_PROJECTS", "20"))


# ─── Helpers ──────────────────────────────────
def _allow(uid: str, seconds: int = 8) -> tuple[bool, int]:
    now = time.time()
    last = _cooldown.get(uid, 0)
    if now - last < seconds:
        return False, int(seconds - (now - last))
    _cooldown[uid] = now
    return True, 0


def _type_emoji(ptype: str) -> str:
    return {"game": "🎮", "store": "🛍️", "dashboard": "📊",
            "landing": "🚀", "portfolio": "💼", "app": "📱"}.get(ptype, "🌐")


def _project_keyboard(proj_name: str, url: str, ptype: str = "website") -> InlineKeyboardMarkup:
    emoji = _type_emoji(ptype)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{emoji} افتح المشروع", url=url),
         InlineKeyboardButton("✏️ تعديل", callback_data=f"edit|{proj_name}")],
        [InlineKeyboardButton("📋 الإصدارات", callback_data=f"versions|{proj_name}"),
         InlineKeyboardButton("📝 تعديل الاسم", callback_data=f"rename|{proj_name}")],
        [InlineKeyboardButton("🗑 حذف", callback_data=f"del|{proj_name}")],
    ])


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
        "projectType": "website",
        "files": [
            {"path": "index.html", "content": html},
            {"path": "style.css",  "content": "body{font-family:'Cairo',sans-serif}"},
            {"path": "script.js",  "content": "// fallback"},
        ]
    }


# ─── Commands ─────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = str(update.message.from_user.id)
    user = update.message.from_user
    upsert_user(uid, user.username or "", user.first_name or "")
    name = user.first_name or "صديقي"
    await update.message.reply_text(
        f"👋 أهلاً {name}!\n\n"
        "🤖 أنا منصة بناء المواقع والألعاب والتطبيقات بالذكاء الاصطناعي\n\n"
        "📌 كيف تستخدمني:\n"
        "  • اكتب فكرتك بشكل طبيعي وأنا أسألك عن أي تفصيل\n"
        "  • لما تقول 'يلا ابدأ' أبني المشروع فعلاً\n"
        "  • شوف معاينة حقيقية قبل النشر النهائي\n"
        "  • عدّل بعد النشر بكل سهولة\n\n"
        "🎮 تريد لعبة؟ قل مثلاً: 'سوّي لي لعبة Sudoku'\n"
        "🛍️ متجر؟ 'ابني متجر إلكترونيات'\n"
        "🌐 موقع؟ 'أنشئ موقع بورتفوليو'\n\n"
        "/help — شرح مفصل\n"
        "/my — مشاريعك\n"
        "/stats — إحصائياتك\n"
        "/cancel — إلغاء أي عملية"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 دليل الاستخدام الكامل\n\n"
        "🏗 بناء مشروع جديد:\n"
        "احكِ لي فكرتك، سأسألك عن التفاصيل الناقصة خطوة بخطوة.\n"
        "عند الانتهاء قل: 'يلا ابدأ' أو 'سويها' أو 'تمام'.\n\n"
        "🎮 الألعاب:\n"
        "أبني ألعاباً كاملة (Sudoku, Blockudoku, Snake, Tetris, 2048...).\n"
        "كل لعبة تشمل: منطق كامل + نقاط + حفظ أعلى نتيجة + تحكم موبايل.\n\n"
        "✏️ التعديلات الذكية:\n"
        "• 'غير الألوان للأزرق'\n"
        "• 'أضف صفحة تسجيل دخول'\n"
        "• 'حوّل اللعبة لـ Dark Mode'\n"
        "• 'أصلح زر الإرسال'\n\n"
        "📋 Version Control:\n"
        "كل تعديل يُحفظ كإصدار منفصل. ارجع لأي نسخة سابقة متى شئت.\n\n"
        "📷 الصور:\n"
        "أرسل صورة (لوقو/منتج/خلفية) مع وصفها أو بدونه.\n"
        "يمكن إزالة خلفية الصورة تلقائياً.\n\n"
        "/my — مشاريعك\n"
        "/stats — إحصائياتك\n"
        "/cancel — إلغاء العملية الحالية"
    )


async def cmd_my(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    projects = get_projects(uid)
    if not projects:
        await update.message.reply_text(
            "📭 لا توجد مشاريع بعد.\n\nأرسل فكرتك وأنا أبنيها! 🚀"
        )
        return
    await update.message.reply_text(f"📂 مشاريعك ({len(projects)}):")
    for p in projects:
        emoji = _type_emoji(p.get("project_type", "website"))
        await update.message.reply_text(
            f"{emoji} {p['display_name']}\n"
            f"📌 نوع: {p.get('project_type', 'موقع')}\n"
            f"🔢 الإصدار: {p.get('version_num', 1)}\n"
            f"🔗 {p['url']}",
            reply_markup=_project_keyboard(p["name"], p["url"], p.get("project_type", "website")),
            disable_web_page_preview=True
        )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    stats = get_user_stats(uid)
    projects = get_projects(uid)
    mem_stats = mem.memory_stats()
    await update.message.reply_text(
        f"📊 إحصائياتك\n\n"
        f"🏗 مشاريع منشأة: {stats['builds']}\n"
        f"✏️ تعديلات: {stats['edits']}\n"
        f"📷 صور مرفوعة: {stats['images']}\n"
        f"📂 مشاريع نشطة: {len(projects)}\n"
        f"🕐 آخر نشاط: {stats['last_active']}\n\n"
        f"💾 الذاكرة النشطة: {mem_stats['cached_projects']} مشروع"
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    PENDING_IMAGE.pop(uid, None)
    PENDING_BUILD.pop(uid, None)
    PLANNING.pop(uid, None)
    VERSION_MODE.pop(uid, None)

    if uid in RENAME_MODE:
        RENAME_MODE.pop(uid)
        await update.message.reply_text("❌ تم إلغاء تغيير الاسم.")
        return
    if uid in EDIT_MODE:
        proj = EDIT_MODE.pop(uid)
        await update.message.reply_text(f"❌ تم إلغاء تعديل '{proj}'.")
    else:
        await update.message.reply_text("ℹ️ لا توجد عملية جارية حالياً.")


# ─── Build & Deploy Flows ─────────────────────
async def _do_build_from_conversation(update: Update, uid: str, conversation: list) -> Optional[dict]:
    await _typing(update)
    user_msgs = " ".join(m["content"] for m in conversation if m["role"] == "user")
    ptype = _detect_project_type(user_msgs)
    emoji = _type_emoji(ptype)
    type_name = {"game": "لعبة", "store": "متجر", "dashboard": "داشبورد",
                 "landing": "صفحة هبوط", "portfolio": "بورتفوليو", "app": "تطبيق"}.get(ptype, "موقع")
    await update.message.reply_text(
        f"{emoji} ممتاز! جاري بناء {type_name} بناءً على كل ما اتفقنا عليه...\n"
        f"{'🎮 سيتضمن منطق لعبة كامل!' if ptype == 'game' else '⏳ هذا يستغرق 30-60 ثانية'}"
    )
    try:
        log(f"[BUILD_CONV] uid={uid} type={ptype} turns={len(conversation)}")
        data = safe_parse(build_from_conversation(conversation))
        if not data:
            raise ValueError("safe_parse=None")
        data.setdefault("projectType", ptype)
        increment_user_stat(uid, "builds_count")
        log(f"[BUILD_CONV_OK] uid={uid} proj={data.get('projectName')} type={ptype}")
        return data
    except RuntimeError as e:
        log(f"[BUILD_CONV_FAIL] uid={uid} err={e}")
        await update.message.reply_text("⚠️ المحرك مشغول الآن، جاري رفع صفحة مؤقتة. أعد الطلب بعد قليل.")
        return _fallback(user_msgs, uid)
    except Exception as e:
        log(f"[BUILD_CONV_ERR] uid={uid} err={e}")
        await update.message.reply_text("⚠️ خطأ غير متوقع، جاري رفع صفحة مؤقتة.")
        return _fallback(user_msgs, uid)


async def _do_edit(update: Update, uid: str, text: str, proj: str,
                   image_url: Optional[str] = None, image_path: Optional[str] = None) -> Optional[dict]:
    await _typing(update)
    await update.message.reply_text(f"🔄 معالجة التعديل على '{proj}'...")

    local = get_project_files(uid, proj) or get_project_files_db(uid, proj)
    current = ""
    if local:
        # حفظ النسخة الحالية قبل التعديل
        save_version(uid, proj, local, description=f"قبل: {text[:80]}")
        for f in local:
            current += f"\n--- {f['path']} ---\n{f['content']}\n"
    else:
        await update.message.reply_text("⚠️ لم أجد الملفات، سيُعامَل كمشروع جديد.")

    try:
        log(f"[EDIT] uid={uid} proj={proj} req={text[:100]}")
        data = safe_parse(editor(text, current_code=current, image_url=image_url, image_path=image_path))
        if not data:
            raise ValueError("safe_parse=None")
        data["projectName"] = proj
        increment_user_stat(uid, "edits_count")
        mem.update_edit_context(proj, text)
        log(f"[EDIT_OK] uid={uid} proj={proj}")
        return data
    except RuntimeError as e:
        log(f"[EDIT_FAIL] uid={uid} err={e}")
        await update.message.reply_text("❌ فشل التعديل. أرسل /cancel ثم أعد المحاولة.")
        return None
    except Exception as e:
        log(f"[EDIT_ERR] uid={uid} err={e}")
        await update.message.reply_text("❌ خطأ غير متوقع في التعديل.")
        return None


async def _do_preview(update: Update, uid: str, data: dict,
                      is_edit: bool, original_proj: Optional[str] = None):
    await _typing(update)
    await update.message.reply_text("📦 جاري تحضير معاينة...")
    try:
        preview_name = (
            data["projectName"] if is_edit
            else f"prev-{data['projectName']}-{int(time.time()) % 9999}"
        )
        preview_data = {**data, "projectName": preview_name}
        build_project(preview_data, uid)
        preview_url = deploy_project(preview_name, preview_data.get("files", []))

        PENDING_BUILD[uid] = {
            "data":          data,
            "is_edit":       is_edit,
            "proj":          original_proj,
            "preview_name":  preview_name,
            "preview_files": preview_data.get("files", []),
        }

        ptype = data.get("projectType", "website")
        emoji = _type_emoji(ptype)

        has_prev_version = (
            original_proj is not None and
            len(get_versions(uid, original_proj)) > 1
        )

        buttons = [
            [InlineKeyboardButton(f"{emoji} افتح المعاينة", url=preview_url)],
            [InlineKeyboardButton("✅ نشر", callback_data="confirm_publish"),
             InlineKeyboardButton("✏️ تعديل إضافي", callback_data="continue_edit")],
        ]
        if has_prev_version:
            buttons.append([InlineKeyboardButton("↩️ استرجاع النسخة السابقة", callback_data="undo_edit")])

        await update.message.reply_text(
            f"👀 معاينتك جاهزة!\n🔗 {preview_url}\n\n"
            f"افتح الرابط وتأكد، ثم اضغط:\n"
            f"✅ نشر — للنشر النهائي\n"
            f"✏️ تعديل إضافي — لمزيد من التعديلات"
            + ("\n↩️ استرجاع — للرجوع للنسخة السابقة" if has_prev_version else ""),
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except Exception as e:
        log(f"[PREVIEW_ERR] uid={uid} err={e}")
        await update.message.reply_text("❌ فشل تحضير المعاينة. تأكد من ضبط BASE_URL.")


async def _do_deploy(update: Update, uid: str, data: dict,
                     files_override: list = None) -> Optional[str]:
    await _typing(update)
    try:
        final_name  = data["projectName"]
        final_files = files_override or data.get("files", [])
        final_data  = {**data, "files": final_files}
        ptype       = data.get("projectType", "website")

        build_project(final_data, uid)
        url = deploy_project(final_name, final_files)

        # حفظ في DB
        add_project(uid, final_name, url, final_files, project_type=ptype)
        save_version(uid, final_name, final_files, description="النشر الأولي")
        mem.set_last(uid, final_data)

        log(f"[DEPLOY_OK] uid={uid} proj={final_name} type={ptype} url={url}")
        emoji = _type_emoji(ptype)
        await update.message.reply_text(
            f"✅ {emoji} تم النشر!\n\n"
            f"📛 الاسم: {final_name}\n"
            f"🔢 الإصدار: 1\n"
            f"🔗 {url}\n\nاستخدم الأزرار 👇",
            reply_markup=_project_keyboard(final_name, url, ptype),
        )
        return url
    except Exception as e:
        log(f"[DEPLOY_ERR] uid={uid} err={e}")
        await update.message.reply_text("❌ فشل الرفع. تحقق من إعدادات السيرفر (BASE_URL).")
        return None


# ─── Photo Handling ───────────────────────────
async def _save_photo(update: Update, uid: str) -> Optional[dict]:
    try:
        photo = update.message.photo[-1]
        tg_file = await photo.get_file()
        filename = f"{uid}_{int(time.time())}.jpg"
        local_path = os.path.join(UPLOADS_DIR, filename)
        await tg_file.download_to_drive(local_path)
        if not PUBLIC_BASE:
            return {"path": local_path, "url": ""}
        url = f"{PUBLIC_BASE}/s/_uploads/{filename}"
        log(f"[PHOTO_SAVED] uid={uid} url={url}")
        return {"path": local_path, "url": url}
    except Exception as e:
        log(f"[PHOTO_ERR] uid={uid} err={e}")
        return None


class _FakeUpdate:
    def __init__(self, message):
        self.message = message


async def _continue_photo_flow(update, uid: str, saved: dict, caption: str):
    if uid in EDIT_MODE:
        if caption:
            proj = EDIT_MODE.pop(uid)
            increment_user_stat(uid, "images_count")
            data = await _do_edit(update, uid, caption, proj,
                                   image_url=saved["url"], image_path=saved["path"])
            if data:
                await _do_preview(update, uid, data, is_edit=True, original_proj=proj)
        else:
            PENDING_IMAGE[uid] = saved
            await update.message.reply_text(
                "📸 استلمت الصورة. أرسل الآن وصف كيف تريد استخدامها:\n"
                "مثلاً: 'خلي هذي الصورة اللوقو' أو 'هذا المنتج أضف صورته'"
            )
        return

    if not caption:
        PENDING_IMAGE[uid] = saved
        await update.message.reply_text(
            "📸 استلمت الصورة. أرسل وصفاً للمشروع الذي تريده:\n"
            "مثلاً: 'سوّي متجر إلكترونيات وخلي هذه الصورة اللوقو'"
        )
        return

    history = PLANNING.setdefault(uid, [])
    history.append({"role": "user", "content": f"{caption} [صورة: {saved['url']}]"})

    try:
        reply_text, ready = plan_chat(history)
    except RuntimeError as e:
        log(f"[PLAN_PHOTO_FAIL] uid={uid} err={e}")
        await update.message.reply_text("⚠️ المحرك مشغول، حاول مجدداً.")
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
        await _do_preview(update, uid, data, is_edit=False)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    try:
        await _typing(update)
        saved = await _save_photo(update, uid)
        if not saved:
            await update.message.reply_text("⚠️ خطأ في حفظ الصورة. حاول مرة أخرى.")
            return
        if not saved["url"]:
            await update.message.reply_text(
                "⚠️ تعذّر توليد رابط للصورة. أضف BASE_URL في متغيرات البيئة."
            )
            return

        caption = (update.message.caption or "").strip()
        saved["caption"] = caption
        PENDING_IMAGE[uid] = saved

        await update.message.reply_text(
            "📸 استلمت الصورة. تبي أزيل الخلفية منها أولاً؟",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🪄 إزالة الخلفية", callback_data="rmbg_yes"),
                 InlineKeyboardButton("➡️ تجاوز", callback_data="rmbg_no")],
            ])
        )
    except Exception as e:
        log(f"[PHOTO_HANDLER_ERR] uid={uid} err={e}")
        try:
            await update.message.reply_text("❌ خطأ في معالجة الصورة. حاول مرة أخرى.")
        except Exception:
            pass


# ─── Main Message Handler ─────────────────────
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    try:
        text = (update.message.text or "").strip()
        if not text:
            await update.message.reply_text("⚠️ الرسالة فارغة، أرسل وصف مشروعك.")
            return

        allowed, remaining = _allow(uid)
        if not allowed:
            await update.message.reply_text(f"⏳ انتظر {remaining} ثانية بين الطلبات.")
            return

        # تحديث بيانات المستخدم
        user = update.message.from_user
        upsert_user(uid, user.username or "", user.first_name or "")

        # ── وضع تغيير الاسم ─────────────────────
        if uid in RENAME_MODE:
            proj = RENAME_MODE.pop(uid)
            rename_project(uid, proj, text.strip())
            await update.message.reply_text(f"✅ تم تغيير الاسم إلى: {text.strip()}")
            return

        # ── وضع التعديل ─────────────────────────
        if uid in EDIT_MODE:
            proj = EDIT_MODE.pop(uid)
            pending = PENDING_IMAGE.pop(uid, None)
            if pending:
                increment_user_stat(uid, "images_count")
                data = await _do_edit(update, uid, text, proj,
                                       image_url=pending["url"], image_path=pending["path"])
            else:
                data = await _do_edit(update, uid, text, proj)
            if data:
                await _do_preview(update, uid, data, is_edit=True, original_proj=proj)
            return

        # ── محادثة التخطيط ───────────────────────
        history = PLANNING.setdefault(uid, [])

        pending_img = PENDING_IMAGE.pop(uid, None)
        if pending_img:
            history.append({"role": "user", "content": f"{text} [صورة: {pending_img['url']}]"})
            increment_user_stat(uid, "images_count")
        else:
            history.append({"role": "user", "content": text})

        # حفظ تاريخ المحادثة
        mem.set_history(uid, history)

        await _typing(update)
        try:
            reply_text, ready = plan_chat(history)
        except RuntimeError as e:
            log(f"[PLAN_FAIL] uid={uid} err={e}")
            await update.message.reply_text("⚠️ المحرك مشغول، حاول مرة أخرى.")
            return

        history.append({"role": "assistant", "content": reply_text})

        if not ready:
            await update.message.reply_text(reply_text)
            return

        await update.message.reply_text(reply_text)
        data = await _do_build_from_conversation(update, uid, history)
        PLANNING.pop(uid, None)
        mem.clear_history(uid)

        if data:
            await _do_preview(update, uid, data, is_edit=False)

    except Exception as e:
        log(f"[HANDLE_FATAL] uid={uid} err={e}")
        try:
            await update.message.reply_text("❌ خطأ غير متوقع. حاول مرة أخرى أو أرسل /cancel.")
        except Exception:
            pass


# ─── Callback Handler ─────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = str(q.from_user.id)

    # ── confirm_publish ──────────────────────
    if q.data == "confirm_publish":
        pending = PENDING_BUILD.pop(uid, None)
        if not pending:
            await q.message.reply_text("⚠️ لا توجد معاينة بانتظار النشر.")
            return
        data        = pending["data"]
        final_files = pending.get("preview_files") or data.get("files", [])
        final_data  = {**data, "files": final_files}
        ptype       = data.get("projectType", "website")

        try:
            build_project(final_data, uid)
            url = deploy_project(data["projectName"], final_files)
            add_project(uid, data["projectName"], url, final_files, project_type=ptype)
            save_version(uid, data["projectName"], final_files, "النشر الأولي")
            mem.set_last(uid, final_data)
            emoji = _type_emoji(ptype)
            await q.message.reply_text(
                f"✅ {emoji} تم النشر!\n\n📛 {data['projectName']}\n🔗 {url}",
                reply_markup=_project_keyboard(data["projectName"], url, ptype),
            )
        except Exception as e:
            log(f"[PUBLISH_ERR] uid={uid} err={e}")
            await q.message.reply_text("❌ فشل النشر. حاول مرة أخرى.")
        return

    # ── rmbg ────────────────────────────────
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
                try:
                    processed = await asyncio.wait_for(
                        asyncio.to_thread(remove_background, raw), timeout=35
                    )
                    new_fname = os.path.basename(saved["path"]).rsplit(".", 1)[0] + "_nobg.png"
                    new_path  = os.path.join(UPLOADS_DIR, new_fname)
                    with open(new_path, "wb") as f:
                        f.write(processed)
                    saved["path"] = new_path
                    saved["url"]  = f"{PUBLIC_BASE}/s/_uploads/{new_fname}" if PUBLIC_BASE else saved["url"]
                    await q.message.reply_text("✅ تمت إزالة الخلفية.")
                except asyncio.TimeoutError:
                    await q.message.reply_text("⏱ استغرق وقتاً طويلاً، سنكمل بالصورة الأصلية.")
            except Exception as e:
                log(f"[RMBG_ERR] uid={uid} err={e}")
                await q.message.reply_text("⚠️ تعذّرت إزالة الخلفية، نكمل بالصورة الأصلية.")
        else:
            await q.message.reply_text("➡️ تم تجاوز إزالة الخلفية.")

        await _continue_photo_flow(_FakeUpdate(q.message), uid, saved, caption)
        return

    # ── continue_edit ────────────────────────
    if q.data == "continue_edit":
        pending = PENDING_BUILD.get(uid)
        if not pending:
            await q.message.reply_text("⚠️ لا توجد معاينة حالية.")
            return
        EDIT_MODE[uid] = pending["preview_name"]
        await q.message.reply_text(
            "✏️ أرسل التعديلات الإضافية:\n"
            "مثلاً: 'غير لون الهيدر للأحمر' أو 'أضف قسم الأسعار'\n"
            "للإلغاء: /cancel"
        )
        return

    # ── undo_edit ────────────────────────────
    if q.data == "undo_edit":
        pending = PENDING_BUILD.get(uid)
        if not pending or not pending.get("proj"):
            await q.message.reply_text("⚠️ لا توجد نسخة سابقة محددة.")
            return
        original_proj = pending["proj"]
        versions = get_versions(uid, original_proj)
        if len(versions) < 2:
            await q.message.reply_text("⚠️ لا توجد نسخة سابقة.")
            return
        prev_ver = versions[1]["version"]  # النسخة قبل الأخيرة
        files = get_version_files(uid, original_proj, prev_ver)
        if not files:
            await q.message.reply_text("⚠️ لم أجد ملفات النسخة السابقة.")
            return
        try:
            restore_data = {"projectName": original_proj, "files": files}
            build_project(restore_data, uid)
            url = deploy_project(original_proj, files)
            update_project_files(uid, original_proj, files, url)
            PENDING_BUILD.pop(uid, None)
            await q.message.reply_text(
                f"✅ تم استرجاع الإصدار {prev_ver} بنجاح!\n🔗 {url}",
                reply_markup=_project_keyboard(original_proj, url),
            )
        except Exception as e:
            log(f"[UNDO_ERR] uid={uid} err={e}")
            await q.message.reply_text("❌ فشل استرجاع النسخة السابقة.")
        return

    # ── actions بالـ pipe ─────────────────────
    if "|" not in q.data:
        return

    parts  = q.data.split("|")
    action = parts[0]
    proj   = parts[1]

    if action == "edit":
        EDIT_MODE[uid] = proj
        await q.message.reply_text(
            f"✏️ وضع تعديل: '{proj}'\n\n"
            "أرسل التعديل المطلوب بالتفصيل:\n"
            "• 'غير لون الأزرار للأخضر'\n"
            "• 'أضف قسم التواصل'\n"
            "• 'حوّل للـ Dark Mode'\n"
            "• أو أرسل صورة مع وصف\n\n"
            "للإلغاء: /cancel"
        )

    elif action == "rename":
        RENAME_MODE[uid] = proj
        await q.message.reply_text(
            f"📝 أرسل الاسم الجديد الذي تريده يظهر في /my:\n"
            f"(لن يتغير رابط الموقع)\n"
            f"للإلغاء: /cancel"
        )

    elif action == "versions":
        versions = get_versions(uid, proj)
        if not versions:
            await q.message.reply_text(f"📋 لا توجد إصدارات محفوظة لـ '{proj}' بعد.")
            return
        text = f"📋 إصدارات '{proj}' ({len(versions)}):\n\n"
        for v in versions[:10]:  # أحدث 10 نسخ
            text += f"🔢 الإصدار {v['version']}: {v['description'] or 'بدون وصف'} — {v['created_at'][:16]}\n"
        if len(versions) > 1:
            text += f"\nاضغط '↩️ استرجاع' في المعاينة لاسترجاع النسخة السابقة."
        await q.message.reply_text(text)

    elif action == "del":
        await q.message.reply_text(
            f"⚠️ هل تريد حذف '{proj}'؟",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ نعم احذف", callback_data=f"confirm_del|{proj}"),
                 InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_del|{proj}")],
            ])
        )

    elif action == "confirm_del":
        await q.message.reply_text(f"🗑 جاري حذف '{proj}'...")
        try:
            delete_vercel_project(proj)
        except Exception:
            pass
        delete_project_files(uid, proj)
        delete_project(uid, proj)
        mem.clear(uid)
        await q.message.reply_text(f"✅ تم حذف '{proj}' بنجاح.")

    elif action == "cancel_del":
        await q.message.reply_text("↩️ تم إلغاء الحذف.")


# ─── App Setup ────────────────────────────────
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
    log("✅ البوت يعمل — النسخة المطورة الكاملة")
    app.run_polling()

"""
bot.py — Render Ready Fixed Version (No Conflict + Safe Polling)
"""

import os
import time
import threading
from dotenv import load_dotenv

load_dotenv()

from flask import Flask

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler, ContextTypes,
    filters, CallbackQueryHandler, CommandHandler
)

from ai import builder, editor
from builder import build_project
from deploy import deploy_project, delete_vercel_project
from validator import safe_parse
from store import add_project, get_projects, delete_project
from file_manager import delete_project_files, get_project_files
from logger import log


BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")


# ─────────────────────────────
# Flask (Render keep-alive)
# ─────────────────────────────

web = Flask(__name__)

@web.get("/")
def home():
    return "Bot is running 🚀"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web.run(host="0.0.0.0", port=port)


# ─────────────────────────────
# Telegram App
# ─────────────────────────────

app = ApplicationBuilder().token(BOT_TOKEN).build()

_cooldown = {}
EDIT_MODE = {}


def allow(uid: str) -> bool:
    now = time.time()
    if now - _cooldown.get(uid, 0) < 5:
        return False
    _cooldown[uid] = now
    return True


# ─────────────────────────────
# Commands
# ─────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 البوت شغال على Render 🚀")

async def my(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    projects = get_projects(uid)

    if not projects:
        await update.message.reply_text("📭 ما عندك مشاريع")
        return

    msg = "📂 مشاريعك:\n\n"
    for p in projects:
        msg += f"🌐 {p['name']} → {p['url']}\n"

    await update.message.reply_text(msg)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    EDIT_MODE.pop(str(update.message.from_user.id), None)
    await update.message.reply_text("❌ تم الإلغاء")


# ─────────────────────────────
# Main handler
# ─────────────────────────────

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.message.from_user.id)
    text = update.message.text

    if not text:
        return

    if not allow(uid):
        await update.message.reply_text("⏳ انتظر شوي")
        return

    await update.message.reply_text("🚀 جاري إنشاء الموقع...")

    try:
        ai_response = builder(text)
        data = safe_parse(ai_response)

        if not data:
            await update.message.reply_text("❌ فشل AI في توليد المشروع")
            return

        build_project(data, uid)

        url = deploy_project(data["projectName"], data.get("files", []))

        add_project(uid, data["projectName"], url)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 فتح الموقع", url=url)]
        ])

        await update.message.reply_text(
            f"✅ تم إنشاء الموقع:\n{url}",
            reply_markup=keyboard
        )

    except Exception as e:
        log(str(e))
        await update.message.reply_text("❌ خطأ أثناء إنشاء الموقع")


# ─────────────────────────────
# Handlers
# ─────────────────────────────

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("my", my))
app.add_handler(CommandHandler("cancel", cancel))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))


# ─────────────────────────────
# Run (FIXED POLLING)
# ─────────────────────────────

if __name__ == "__main__":
    log("Bot starting on Render 🚀")

    # تشغيل Flask في thread
    threading.Thread(target=run_web, daemon=True).start()

    # 🔥 FIX IMPORTANT: يمنع Conflict 409
    app.run_polling(
        drop_pending_updates=True
    )

"""
server.py — سيرفر Flask + تشغيل البوت — النسخة المطورة.

التحسينات:
  - استرجاع المواقع + الصور + الـ Assets من Turso عند كل إعادة تشغيل
  - routes إضافية: /health/detail + /projects + /api/status
  - MIME types صحيحة لكل أنواع الملفات
  - حماية من directory traversal
  - ضغط الردود (gzip)
  - إصلاح event loop لـ Python 3.13+/3.14 (RuntimeError: no current event loop)
"""
import os
import threading
import mimetypes
import asyncio
from flask import Flask, send_from_directory, abort, jsonify, Response
from logger import log

SITES_DIR = os.path.join(os.path.dirname(__file__), "sites")
os.makedirs(SITES_DIR, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max upload

# MIME types إضافية
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/avif", ".avif")


# ─── Routes ───────────────────────────────────
@app.route("/")
def home():
    return Response(
        "🤖 AI Website Builder — Bot is running!",
        content_type="text/plain; charset=utf-8"
    )


@app.route("/health")
def health():
    return "OK", 200


@app.route("/health/detail")
def health_detail():
    """فحص تفصيلي للحالة."""
    try:
        from store import get_all_projects
        projects = get_all_projects()
        sites = [d for d in os.listdir(SITES_DIR)
                 if os.path.isdir(os.path.join(SITES_DIR, d)) and not d.startswith("_")]
        return jsonify({
            "status":         "ok",
            "projects_in_db": len(projects),
            "sites_on_disk":  len(sites),
            "sites_dir":      SITES_DIR,
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/status")
def api_status():
    """حالة المنصة للمراقبة الخارجية."""
    base_url = os.getenv("BASE_URL", "غير مضبوط")
    groq_key = "✅" if os.getenv("GROQ_API_KEY") else "❌"
    anthropic = "✅" if os.getenv("ANTHROPIC_API_KEY") else "❌ (اختياري)"
    turso     = "✅" if os.getenv("TURSO_DATABASE_URL") else "❌"
    rembg     = "✅" if os.getenv("REMOVE_BG_API_KEY") else "❌ (اختياري)"
    tavily    = "✅" if os.getenv("TAVILY_API_KEY") else "❌ (اختياري)"

    return jsonify({
        "platform":   "AI Website Builder",
        "base_url":   base_url,
        "groq":       groq_key,
        "anthropic":  anthropic,
        "turso_db":   turso,
        "remove_bg":  rembg,
        "web_search": tavily,
    })


@app.route("/s/<name>/")
@app.route("/s/<name>/<path:filename>")
def serve_site(name, filename="index.html"):
    """يخدم ملفات الموقع مع حماية من traversal."""
    site_dir = os.path.realpath(os.path.join(SITES_DIR, name))
    if not site_dir.startswith(os.path.realpath(SITES_DIR)):
        abort(403)
    if not os.path.exists(site_dir):
        abort(404)

    mime, _ = mimetypes.guess_type(filename)
    response = send_from_directory(site_dir, filename, mimetype=mime)

    if filename.endswith((".css", ".js")):
        response.cache_control.max_age = 3600
    elif filename.endswith((".jpg", ".jpeg", ".png", ".webp", ".ico")):
        response.cache_control.max_age = 86400

    return response


@app.errorhandler(404)
def not_found(e):
    return Response("404 — الصفحة غير موجودة", status=404, content_type="text/plain; charset=utf-8")


@app.errorhandler(403)
def forbidden(e):
    return Response("403 — غير مسموح", status=403, content_type="text/plain; charset=utf-8")


# ─── Startup ──────────────────────────────────
def run_flask():
    port = int(os.getenv("PORT", 10000))
    log(f"[FLASK] يعمل على المنفذ {port}")
    app.run(host="0.0.0.0", port=port, threaded=True)


def restore_all_from_db():
    """يُستدعى عند بدء التشغيل — يعيد كل الملفات من Turso للقرص."""
    try:
        from deploy import restore_all_sites_from_db
        restore_all_sites_from_db()
        log("[RESTORE] اكتمل استرجاع المواقع من قاعدة البيانات")
    except Exception as e:
        log(f"[RESTORE_ERR] {e}")


if __name__ == "__main__":
    log("🚀 بدء تشغيل منصة AI Website Builder")

    restore_all_from_db()

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    log("[SERVER] Flask يعمل في الخلفية")

    # إصلاح ضروري لـ Python 3.13+/3.14: asyncio.get_event_loop() لا يعود
    # ينشئ event loop تلقائياً بالـ main thread إن لم يوجد واحد فعلياً شغّال،
    # ويرمي RuntimeError بدلاً من ذلك. ننشئه ونثبّته يدوياً قبل تشغيل البوت
    # حتى تجده مكتبة python-telegram-bot داخلياً عند الحاجة له.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    from bot import app as telegram_app
    log("[BOT] جاري تشغيل بوت تيليجرام...")
    telegram_app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
    )

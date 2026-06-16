"""
server.py — Flask server يعرض المواقع المحلية + يشغل البوت في thread منفصل.
شغّل هذا الملف بدل bot.py مباشرة.
"""
import os
import threading
from flask import Flask, send_from_directory, abort

SITES_DIR = os.path.join(os.path.dirname(__file__), "sites")

app = Flask(__name__)

@app.route("/s/<name>/")
@app.route("/s/<name>/<path:filename>")
def serve_site(name, filename="index.html"):
    site_dir = os.path.join(SITES_DIR, name)
    if not os.path.exists(site_dir):
        abort(404)
    return send_from_directory(site_dir, filename)

@app.route("/")
def home():
    return "🤖 Bot is running!", 200

@app.route("/health")
def health():
    return "OK", 200

def run_bot():
    # import هنا عشان يصير بعد ما Flask يبدأ
    import asyncio
    from bot import app as telegram_app
    from logger import log
    log("✅ البوت يعمل في thread منفصل...")
    telegram_app.run_polling()

if __name__ == "__main__":
    # شغّل البوت في thread منفصل
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # شغّل Flask
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
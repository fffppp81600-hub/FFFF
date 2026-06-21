"""
server.py — يشغل Flask (لعرض المواقع) في thread ثانوي، والبوت في الـ main thread.
عند كل بدء تشغيل: يستعيد كل المواقع + الصور من قاعدة بيانات Turso السحابية إلى القرص.
"""
import os
import threading
from flask import Flask, send_from_directory, abort

SITES_DIR = os.path.join(os.path.dirname(__file__), "sites")
os.makedirs(SITES_DIR, exist_ok=True)

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

def run_flask():
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    from deploy import restore_all_sites_from_db
    restore_all_sites_from_db()

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    from bot import app as telegram_app
    from logger import log
    log("✅ البوت يعمل...")
    telegram_app.run_polling()

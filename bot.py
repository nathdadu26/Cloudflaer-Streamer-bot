import os
import time
import asyncio
import logging
import boto3
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ───────── LOAD ENV ─────────
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_BUCKET = os.getenv("R2_BUCKET_NAME")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL")
VLC_WORKER = os.getenv("VLC_WORKER")

PORT = int(os.getenv("PORT", 8000))

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ───────── LOGGING ─────────
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ───────── HEALTH CHECK SERVER ─────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    log.info(f"Health check server running on port {PORT}")
    server.serve_forever()

threading.Thread(
    target=start_health_server,
    daemon=True
).start()

# ───────── R2 CLIENT ─────────
s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{CF_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    region_name="auto"
)

# ───────── BOT ─────────
app = Client(
    "r2-uploader-bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ───────── HELPERS ─────────
def human_size(size):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024

def progress_bar(p):
    filled = int(p // 10)
    return "█" * filled + "░" * (10 - filled)

# ───────── START ─────────
@app.on_message(filters.command("start"))
async def start(_, message):
    await message.reply_text(
        "🤖 Cloudflare R2 Upload Bot\n\n"
        "Send any video or file 📁\n"
        "I will upload it to cloud ☁️"
    )

# ───────── MEDIA HANDLER ─────────
@app.on_message(filters.video | filters.document)
async def handle_media(_, message):
    media = message.video or message.document

    file_name = media.file_name or f"{media.file_unique_id}.bin"
    file_size = media.file_size
    local_path = os.path.join(DOWNLOAD_DIR, file_name)

    status = await message.reply_text("🚀 Downloading...")
    start_time = time.time()

    async def download_progress(current, total):
        percent = current * 100 / total
        speed = current / max(time.time() - start_time, 1)
        eta = (total - current) / max(speed, 1)

        text = (
            "🚀 Downloading...\n\n"
            f"📁 `{file_name}`\n"
            f"👀 {human_size(total)}\n"
            f"⚡ {human_size(speed)}/s\n"
            f"⏳ {int(eta)} sec\n"
            f"`[{progress_bar(percent)}] {percent:.1f}%`"
        )

        try:
            await status.edit_text(text)
        except:
            pass

    await message.download(
        file_name=local_path,
        progress=download_progress
    )

    # ───────── UPLOAD TO R2 ─────────
    await status.edit_text("☁️ Uploading to Cloudflare R2...")

    s3.upload_file(
        local_path,
        R2_BUCKET,
        file_name,
        ExtraArgs={
            "ACL": "public-read",
            "ContentType": "video/mp4"
        }
    )

    os.remove(local_path)

    public_link = f"{R2_PUBLIC_URL}/{file_name}"
    vlc_link = f"{VLC_WORKER}/?url={public_link}"

    caption = (
        "✅ Upload Complete!\n\n"
        f"📁 File Name: `{file_name}`\n"
        f"👀 File Size: `{human_size(file_size)}`"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("▶️ Play with VLC 📺", url=vlc_link)],
            [InlineKeyboardButton("⬇️ Download", url=public_link)]
        ]
    )

    await status.edit_text(
        caption,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

    log.info("Upload completed: %s", file_name)

# ───────── RUN ─────────
if __name__ == "__main__":
    print("🤖 Bot + Health server running...")
    app.run()


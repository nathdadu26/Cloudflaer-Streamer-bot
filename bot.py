import os
import uuid
import logging
import boto3
from dotenv import load_dotenv
from pyrogram import Client, filters

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL")

logging.basicConfig(level=logging.INFO)

# R2 client
s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{CF_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY
)

app = Client(
    "r2_uploader_bot",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH
)

@app.on_message(filters.command("start"))
async def start(_, message):
    await message.reply(
        "📤 Send me a video or large file\n"
        "I will upload it to cloud & give you a link 🔗"
    )

@app.on_message(filters.video | filters.document)
async def upload_file(_, message):
    media = message.video or message.document

    await message.reply("⬇️ Downloading file from Telegram...")

    file_ext = os.path.splitext(media.file_name or "video.mp4")[1]
    file_name = f"{uuid.uuid4()}{file_ext}"
    local_path = f"downloads/{file_name}"

    os.makedirs("downloads", exist_ok=True)

    await message.download(file_name=local_path)

    await message.reply("☁️ Uploading to Cloudflare R2...")

    content_type = media.mime_type or "application/octet-stream"

    s3.upload_file(
        local_path,
        R2_BUCKET_NAME,
        file_name,
        ExtraArgs={"ContentType": content_type}
    )

    os.remove(local_path)

    public_link = f"{R2_PUBLIC_URL}/{file_name}"

    await message.reply(
        "✅ Upload Successful!\n\n"
        f"🔗 Download Link:\n{public_link}"
    )

app.run()

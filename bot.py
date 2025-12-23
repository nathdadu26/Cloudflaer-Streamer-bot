import os
import asyncio
import math
import time
import logging
import boto3
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ─── LOAD ENV ───────────────────────────────────────────────
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

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ─── LOGGING ───────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ─── R2 CLIENT ─────────────────────────────────────────────
s3 = boto3.client(
    "s3",
    endpoint_url=f"https://{CF_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    region_name="auto",
)

# ─── BOT ──────────────────────────────────────────────────
app = Client(
    "r2-uploader-bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ─── HELPERS ──────────────────────────────────────────────
def human_size(size):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024

def progress_bar(percent):
    filled = int(percent // 10)
    return "█" * filled + "░" * (10 - filled)

# ─── START ────────────────────────────────────────────────
@app.on_message(filters.command("start"))
async def start(_, message):
    await message.reply_text("🤖 **Send video or file to upload on Cloudflare R2**")

# ─── MEDIA HANDLER ────────────────────────────────────────
@app.on_message(filters.video | filters.document)
async def handle_media(_, message):
    media = message.video or message.document

    file_name = media.file_name or f"{media.file_unique_id}.bin"
    file_size = media.file_size
    local_path = os.path.join(DOWNLOAD_DIR, file_name)

    status = await message.reply_text("🚀 **Downloading...**")

    start_time = time.time()

    async def download_progress(current, total):
        percent = current * 100 / total
        speed = current / (time.time() - start_time + 0.1)
        eta = (total - current) / (speed + 1)

        text = (
            "🚀 **Downloading...**\n\n"
            f"📁 `{file_name}`\n"
            f"👀 {human_size(total)}\n"
            f"⚡ {human_size(speed)}/s\n"
            f"⏳ {int(eta)} sec\n"
            f"`[{progress_bar(percent)}] {percent:.1f}%`"
        )
        await status.edit_text(text)

    await message.download(
        file_name=local_path,
        progress=download_progress
    )

    # ─── UPLOAD TO R2 ──────────────────────────────────────
    await status.edit_text("☁️ **Uploading to Cloudflare R2...**")

    s3.upload_file(
        local_path,
        R2_BUCKET,
        file_name,
        ExtraArgs={
            "ContentType": "video/mp4",
            "ACL": "public-read"
        }
    )

    os.remove(local_path)

    public_link = f"{R2_PUBLIC_URL}/{file_name}"
    vlc_link = f"{VLC_WORKER}/?url={public_link}"

    caption = (
        "✅ **Upload Complete !**\n\n"
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

    log.info("Uploaded: %s", file_name)

# ─── RUN ─────────────────────────────────────────────────
if __name__ == "__main__":
    print("🤖 R2 Upload Bot Running...")
    app.run()
        "I will upload it to cloud 🎬⬇️\n\n"
        "Commands:\n/myfiles - View your files"
    )

@app.on_message(filters.video | filters.document)
async def handle_media(_, message):
    media = message.video or message.document
    original_name = media.file_name or f"file_{message.id}.mp4"
    safe_name = original_name.replace(" ", "_")
    user_folder = str(message.from_user.id)
    r2_key = f"{user_folder}/{safe_name}"
    local_path = os.path.join(DOWNLOAD_DIR, safe_name)
    status_msg = await message.reply("🚀 Downloading...")
    start_time = time.time()

    await message.download(
        file_name=local_path,
        progress=progress,
        progress_args=(status_msg, start_time, "Downloading", safe_name)
    )

    file_size = os.path.getsize(local_path)
    upload_progress = UploadProgress(status_msg, safe_name, file_size)

    s3.upload_file(
        local_path,
        R2_BUCKET_NAME,
        r2_key,
        Callback=upload_progress,
        ExtraArgs={"ContentType": media.mime_type or "application/octet-stream"}
    )

    os.remove(local_path)
    public_link = f"{R2_PUBLIC_URL}/{r2_key}"
    worker_url = f"https://play-in-app.ftolbots.workers.dev/?url={public_link}"
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶️ Play In VLC", url=worker_url),
            InlineKeyboardButton("⬇️ Download", url=public_link),
        ],
    ])

    await status_msg.edit(
        f"📁 Completed! File Name: `{safe_name}`\n🎬 Play in -",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@app.on_message(filters.command("myfiles"))
async def myfiles(_, message):
    user_id = str(message.from_user.id)
    try:
        response = s3.list_objects_v2(Bucket=R2_BUCKET_NAME, Prefix=f"{user_id}/")
        if 'Contents' not in response or len(response['Contents']) == 0:
            await message.reply("📁 No files yet!")
            return
        files_text = "📁 Your Files:\n\n"
        for obj in response['Contents']:
            file_key = obj['Key']
            file_name = file_key.replace(f"{user_id}/", "")
            file_size = obj['Size']
            file_url = f"{R2_PUBLIC_URL}/{file_key}"
            files_text += f"📄 `{file_name}`\nSize: {human_bytes(file_size)}\n[Download]({file_url})\n`/delete_file {file_name}`\n\n"
        await message.reply(files_text, disable_web_page_preview=True)
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("delete_file"))
async def delete_file(_, message):
    user_id = str(message.from_user.id)
    is_admin = user_id == str(ADMIN_ID)
    try:
        if is_admin and len(message.command) == 3:
            target_user_id = message.command[1]
            file_name = message.command[2]
        else:
            target_user_id = user_id
            file_name = message.command[1]
    except IndexError:
        await message.reply("❌ Usage: `/delete_file filename.mp4`")
        return
    
    file_key = f"{target_user_id}/{file_name}"
    try:
        if target_user_id != user_id and not is_admin:
            await message.reply("❌ Can only delete own files!")
            return
        response = s3.list_objects_v2(Bucket=R2_BUCKET_NAME, Prefix=file_key)
        if 'Contents' not in response or len(response['Contents']) == 0:
            await message.reply(f"❌ File not found!")
            return
        s3.delete_object(Bucket=R2_BUCKET_NAME, Key=file_key)
        await message.reply(f"✅ File deleted!")
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("all_files"))
async def all_files(_, message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ Admin only!")
        return
    try:
        response = s3.list_objects_v2(Bucket=R2_BUCKET_NAME)
        if 'Contents' not in response:
            await message.reply("📁 No files!")
            return
        total_size = 0
        user_stats = {}
        for obj in response['Contents']:
            file_key = obj['Key']
            file_size = obj['Size']
            total_size += file_size
            user_id = file_key.split('/')[0]
            if user_id not in user_stats:
                user_stats[user_id] = {'count': 0, 'size': 0}
            user_stats[user_id]['count'] += 1
            user_stats[user_id]['size'] += file_size
        
        files_text = f"📊 Storage Stats:\n💾 Total: {human_bytes(total_size)}\n👥 Users: {len(user_stats)}\n📁 Files: {len(response['Contents'])}\n\n"
        sorted_users = sorted(user_stats.items(), key=lambda x: x[1]['size'], reverse=True)
        for uid, stats in sorted_users:
            files_text += f"👤 `{uid}`: {stats['count']} files, {human_bytes(stats['size'])}\n"
        await message.reply(files_text)
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("total_files"))
async def total_files(_, message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ Admin only!")
        return
    try:
        response = s3.list_objects_v2(Bucket=R2_BUCKET_NAME)
        if 'Contents' not in response:
            await message.reply("📁 No files!")
            return
        files_text = ""
        for obj in response['Contents']:
            file_key = obj['Key']
            file_name = file_key.split('/')[-1]
            file_size = obj['Size']
            user_id = file_key.split('/')[0]
            files_text += f"📁 `{file_name}`\n💾 {human_bytes(file_size)}\n`/delete_file {user_id} {file_name}`\n\n"
        await message.reply(files_text)
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

async def health_check(request):
    return web.Response(text="OK", status=200)

async def start_health_server():
    web_app = web.Application()
    web_app.router.add_get('/health', health_check)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()
    print("🔥 Health check on :8000")

async def main():
    print("🤖 Bot starting...")
    await start_health_server()
    async with app:
        print("🤖 Bot running!")
        await app.listen()

if __name__ == "__main__":
    asyncio.run(main())            f"🚀 Uploading...\n\n"
            f"📁 File Name: `{self.filename}`\n"
            f"👀 File Size: {human_bytes(self.filesize)}\n"
            f"⚡ Speed: {human_bytes(speed)}/s\n"
            f"⏳ ETA: {math.ceil(eta)} sec\n\n"
            f"`{bar}` {percent:.2f}%"
        )

        try:
            asyncio.get_event_loop().create_task(
                self.msg.edit(text)
            )
        except:
            pass

# ---------------- COMMANDS ----------------
@app.on_message(filters.command("start"))
async def start(_, message):
    await message.reply(
        "📤 Send me a video or file\n"
        "I will upload it to cloud and give you play/download buttons 🎬⬇️\n\n"
        "Commands:\n"
        "/myfiles - View all your uploaded files"
    )

# ---------------- MEDIA HANDLER ----------------
@app.on_message(filters.video | filters.document)
async def handle_media(_, message):
    media = message.video or message.document

    original_name = media.file_name or f"file_{message.id}.mp4"
    safe_name = original_name.replace(" ", "_")

    user_folder = str(message.from_user.id)
    r2_key = f"{user_folder}/{safe_name}"
    local_path = os.path.join(DOWNLOAD_DIR, safe_name)

    status_msg = await message.reply("🚀 Downloading...")

    start_time = time.time()

    # -------- DOWNLOAD --------
    await message.download(
        file_name=local_path,
        progress=progress,
        progress_args=(
            status_msg,
            start_time,
            "Downloading",
            safe_name
        )
    )

    file_size = os.path.getsize(local_path)

    # -------- UPLOAD --------
    upload_progress = UploadProgress(
        status_msg,
        safe_name,
        file_size
    )

    s3.upload_file(
        local_path,
        R2_BUCKET_NAME,
        r2_key,
        Callback=upload_progress,
        ExtraArgs={"ContentType": media.mime_type or "application/octet-stream"}
    )

    os.remove(local_path)

    public_link = f"{R2_PUBLIC_URL}/{r2_key}"

    # -------- INLINE BUTTONS --------
    worker_url = f"https://play-in-app.ftolbots.workers.dev/?url={public_link}"
    
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("▶️ Play In VLC", url=worker_url),
                InlineKeyboardButton("⬇️ Download", url=public_link),
            ],
        ]
    )

    response_text = (
        f"📁 Completed! File Name: `{safe_name}`\n"
        f"🎬 Play in -"
    )

    await status_msg.edit(
        response_text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@app.on_message(filters.command("myfiles"))
async def myfiles(_, message):
    user_id = str(message.from_user.id)
    
    try:
        # List all files in user's folder
        response = s3.list_objects_v2(
            Bucket=R2_BUCKET_NAME,
            Prefix=f"{user_id}/"
        )
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            await message.reply("📁 You haven't uploaded any files yet!")
            return
        
        files_text = "📁 **Your Uploaded Files:**\n\n"
        
        for obj in response['Contents']:
            file_key = obj['Key']
            file_name = file_key.replace(f"{user_id}/", "")
            file_size = obj['Size']
            file_url = f"{R2_PUBLIC_URL}/{file_key}"
            
            # Format file size
            size_str = human_bytes(file_size)
            
            files_text += f"📄 `{file_name}`\n"
            files_text += f"   Size: {size_str}\n"
            files_text += f"   [Download]({file_url})\n"
            files_text += f"   `/delete_file {file_name}`\n\n"
        
        await message.reply(files_text, disable_web_page_preview=True)
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("delete_file"))
async def delete_file(_, message):
    user_id = str(message.from_user.id)
    is_admin = user_id == str(ADMIN_ID)
    
    # Get filename and optional user_id from command
    try:
        if is_admin and len(message.command) == 3:
            # Admin format: /delete_file user_id filename
            target_user_id = message.command[1]
            file_name = message.command[2]
        else:
            # User format: /delete_file filename
            target_user_id = user_id
            file_name = message.command[1]
    except IndexError:
        if is_admin:
            await message.reply("❌ Usage:\nUser: `/delete_file filename.mp4`\nAdmin: `/delete_file user_id filename.mp4`")
        else:
            await message.reply("❌ Usage: `/delete_file filename.mp4`")
        return
    
    file_key = f"{target_user_id}/{file_name}"
    
    try:
        # Check if user is deleting their own file or is admin
        if target_user_id != user_id and not is_admin:
            await message.reply("❌ You can only delete your own files!")
            return
        
        # Check if file exists
        response = s3.list_objects_v2(
            Bucket=R2_BUCKET_NAME,
            Prefix=file_key
        )
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            await message.reply(f"❌ File '{file_name}' not found!")
            return
        
        # Delete the file
        s3.delete_object(Bucket=R2_BUCKET_NAME, Key=file_key)
        
        if is_admin and target_user_id != user_id:
            await message.reply(f"✅ File '{file_name}' from user {target_user_id} deleted successfully!")
        else:
            await message.reply(f"✅ File '{file_name}' deleted successfully!")
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("all_files"))
async def all_files(_, message):
    # Admin only
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ You don't have permission to use this command!")
        return
    
    try:
        # List all files in bucket
        response = s3.list_objects_v2(Bucket=R2_BUCKET_NAME)
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            await message.reply("📁 No files in storage!")
            return
        
        total_size = 0
        user_stats = {}
        
        # Calculate stats
        for obj in response['Contents']:
            file_key = obj['Key']
            file_size = obj['Size']
            total_size += file_size
            
            # Extract user ID from key
            user_id = file_key.split('/')[0]
            
            if user_id not in user_stats:
                user_stats[user_id] = {'count': 0, 'size': 0}
            
            user_stats[user_id]['count'] += 1
            user_stats[user_id]['size'] += file_size
        
        # Build response
        files_text = "📊 **All Files Statistics:**\n\n"
        files_text += f"💾 **Total Storage Used:** {human_bytes(total_size)}\n"
        files_text += f"👥 **Total Users:** {len(user_stats)}\n"
        files_text += f"📁 **Total Files:** {len(response['Contents'])}\n\n"
        
        files_text += "**Per User Breakdown:**\n\n"
        
        # Sort by size (largest first)
        sorted_users = sorted(user_stats.items(), key=lambda x: x[1]['size'], reverse=True)
        
        for user_id, stats in sorted_users:
            files_text += f"👤 User ID: `{user_id}`\n"
            files_text += f"   Files: {stats['count']}\n"
            files_text += f"   Storage: {human_bytes(stats['size'])}\n\n"
        
        await message.reply(files_text)
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("total_files"))
async def total_files(_, message):
    # Admin only
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ You don't have permission to use this command!")
        return
    
    try:
        # List all files in bucket
        response = s3.list_objects_v2(Bucket=R2_BUCKET_NAME)
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            await message.reply("📁 No files in storage!")
            return
        
        files_text = ""
        
        for obj in response['Contents']:
            file_key = obj['Key']
            file_name = file_key.split('/')[-1]
            file_size = obj['Size']
            user_id = file_key.split('/')[0]
            
            files_text += f"📁 File: `{file_name}`\n"
            files_text += f"💾 Size: {human_bytes(file_size)}\n"
            files_text += f"/delete_file {user_id} {file_name}\n\n"
        
        await message.reply(files_text)
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

# -------- HEALTH CHECK SERVER --------
async def health_check(request):
    return web.Response(text="OK", status=200)

async def start_health_server():
    web_app = web.Application()
    web_app.router.add_get('/health', health_check)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()
    print("🔥 Health check server started on port 8000")

# -------- RUN ----------------
async def main():
    print("🤖 Bot is starting...")
    
    # Start health check server
    await start_health_server()
    
    # Start bot
    async with app:
        print("🤖 Bot is running...")
        await app.listen()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped")            f"🚀 Uploading...\n\n"
            f"📁 File Name: `{self.filename}`\n"
            f"👀 File Size: {human_bytes(self.filesize)}\n"
            f"⚡ Speed: {human_bytes(speed)}/s\n"
            f"⏳ ETA: {math.ceil(eta)} sec\n\n"
            f"`{bar}` {percent:.2f}%"
        )

        try:
            asyncio.get_event_loop().create_task(
                self.msg.edit(text)
            )
        except:
            pass

# ---------------- COMMANDS ----------------
@app.on_message(filters.command("start"))
async def start(_, message):
    await message.reply(
        "📤 Send me a video or file\n"
        "I will upload it to cloud and give you play/download buttons 🎬⬇️\n\n"
        "Commands:\n"
        "/myfiles - View all your uploaded files"
    )

# ---------------- MEDIA HANDLER ----------------
@app.on_message(filters.video | filters.document)
async def handle_media(_, message):
    media = message.video or message.document

    original_name = media.file_name or f"file_{message.id}.mp4"
    safe_name = original_name.replace(" ", "_")

    user_folder = str(message.from_user.id)
    r2_key = f"{user_folder}/{safe_name}"
    local_path = os.path.join(DOWNLOAD_DIR, safe_name)

    status_msg = await message.reply("🚀 Downloading...")

    start_time = time.time()

    # -------- DOWNLOAD --------
    await message.download(
        file_name=local_path,
        progress=progress,
        progress_args=(
            status_msg,
            start_time,
            "Downloading",
            safe_name
        )
    )

    file_size = os.path.getsize(local_path)

    # -------- UPLOAD --------
    upload_progress = UploadProgress(
        status_msg,
        safe_name,
        file_size
    )

    s3.upload_file(
        local_path,
        R2_BUCKET_NAME,
        r2_key,
        Callback=upload_progress,
        ExtraArgs={"ContentType": media.mime_type or "application/octet-stream"}
    )

    os.remove(local_path)

    public_link = f"{R2_PUBLIC_URL}/{r2_key}"

    # -------- INLINE BUTTONS --------
    worker_url = f"https://play-in-app.ftolbots.workers.dev/?url={public_link}"
    
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("▶️ Play In VLC", url=worker_url),
                InlineKeyboardButton("⬇️ Download", url=public_link),
            ],
        ]
    )

    response_text = (
        f"📁 Completed! File Name: `{safe_name}`\n"
        f"🎬 Play in -"
    )

    await status_msg.edit(
        response_text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@app.on_message(filters.command("myfiles"))
async def myfiles(_, message):
    user_id = str(message.from_user.id)
    
    try:
        # List all files in user's folder
        response = s3.list_objects_v2(
            Bucket=R2_BUCKET_NAME,
            Prefix=f"{user_id}/"
        )
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            await message.reply("📁 You haven't uploaded any files yet!")
            return
        
        files_text = "📁 **Your Uploaded Files:**\n\n"
        
        for obj in response['Contents']:
            file_key = obj['Key']
            file_name = file_key.replace(f"{user_id}/", "")
            file_size = obj['Size']
            file_url = f"{R2_PUBLIC_URL}/{file_key}"
            
            # Format file size
            size_str = human_bytes(file_size)
            
            files_text += f"📄 `{file_name}`\n"
            files_text += f"   Size: {size_str}\n"
            files_text += f"   [Download]({file_url})\n"
            files_text += f"   `/delete_file {file_name}`\n\n"
        
        await message.reply(files_text, disable_web_page_preview=True)
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("delete_file"))
async def delete_file(_, message):
    user_id = str(message.from_user.id)
    is_admin = user_id == str(ADMIN_ID)
    
    # Get filename and optional user_id from command
    try:
        if is_admin and len(message.command) == 3:
            # Admin format: /delete_file user_id filename
            target_user_id = message.command[1]
            file_name = message.command[2]
        else:
            # User format: /delete_file filename
            target_user_id = user_id
            file_name = message.command[1]
    except IndexError:
        if is_admin:
            await message.reply("❌ Usage:\nUser: `/delete_file filename.mp4`\nAdmin: `/delete_file user_id filename.mp4`")
        else:
            await message.reply("❌ Usage: `/delete_file filename.mp4`")
        return
    
    file_key = f"{target_user_id}/{file_name}"
    
    try:
        # Check if user is deleting their own file or is admin
        if target_user_id != user_id and not is_admin:
            await message.reply("❌ You can only delete your own files!")
            return
        
        # Check if file exists
        response = s3.list_objects_v2(
            Bucket=R2_BUCKET_NAME,
            Prefix=file_key
        )
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            await message.reply(f"❌ File '{file_name}' not found!")
            return
        
        # Delete the file
        s3.delete_object(Bucket=R2_BUCKET_NAME, Key=file_key)
        
        if is_admin and target_user_id != user_id:
            await message.reply(f"✅ File '{file_name}' from user {target_user_id} deleted successfully!")
        else:
            await message.reply(f"✅ File '{file_name}' deleted successfully!")
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("all_files"))
async def all_files(_, message):
    # Admin only
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ You don't have permission to use this command!")
        return
    
    try:
        # List all files in bucket
        response = s3.list_objects_v2(Bucket=R2_BUCKET_NAME)
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            await message.reply("📁 No files in storage!")
            return
        
        total_size = 0
        user_stats = {}
        
        # Calculate stats
        for obj in response['Contents']:
            file_key = obj['Key']
            file_size = obj['Size']
            total_size += file_size
            
            # Extract user ID from key
            user_id = file_key.split('/')[0]
            
            if user_id not in user_stats:
                user_stats[user_id] = {'count': 0, 'size': 0}
            
            user_stats[user_id]['count'] += 1
            user_stats[user_id]['size'] += file_size
        
        # Build response
        files_text = "📊 **All Files Statistics:**\n\n"
        files_text += f"💾 **Total Storage Used:** {human_bytes(total_size)}\n"
        files_text += f"👥 **Total Users:** {len(user_stats)}\n"
        files_text += f"📁 **Total Files:** {len(response['Contents'])}\n\n"
        
        files_text += "**Per User Breakdown:**\n\n"
        
        # Sort by size (largest first)
        sorted_users = sorted(user_stats.items(), key=lambda x: x[1]['size'], reverse=True)
        
        for user_id, stats in sorted_users:
            files_text += f"👤 User ID: `{user_id}`\n"
            files_text += f"   Files: {stats['count']}\n"
            files_text += f"   Storage: {human_bytes(stats['size'])}\n\n"
        
        await message.reply(files_text)
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("total_files"))
async def total_files(_, message):
    # Admin only
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ You don't have permission to use this command!")
        return
    
    try:
        # List all files in bucket
        response = s3.list_objects_v2(Bucket=R2_BUCKET_NAME)
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            await message.reply("📁 No files in storage!")
            return
        
        files_text = ""
        
        for obj in response['Contents']:
            file_key = obj['Key']
            file_name = file_key.split('/')[-1]
            file_size = obj['Size']
            user_id = file_key.split('/')[0]
            
            files_text += f"📁 File: `{file_name}`\n"
            files_text += f"💾 Size: {human_bytes(file_size)}\n"
            files_text += f"/delete_file {user_id} {file_name}\n\n"
        
        await message.reply(files_text)
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

# -------- HEALTH CHECK SERVER --------
async def health_check(request):
    return web.Response(text="OK", status=200)

async def start_health_server():
    web_app = web.Application()
    web_app.router.add_get('/health', health_check)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()
    print("🔥 Health check server started on port 8000")

# -------- RUN ----------------
async def main():
    print("🤖 Bot is starting...")
    
    # Start health check server
    await start_health_server()
    
    # Start bot
    async with app:
        print("🤖 Bot is running...")
        await app.listen()

if __name__ == "__main__":
    asyncio.run(main())            f"📁 File Name: `{self.filename}`\n"
            f"👀 File Size: {human_bytes(self.filesize)}\n"
            f"⚡ Speed: {human_bytes(speed)}/s\n"
            f"⏳ ETA: {math.ceil(eta)} sec\n\n"
            f"`{bar}` {percent:.2f}%"
        )

        try:
            import asyncio
            asyncio.get_event_loop().create_task(
                self.msg.edit(text)
            )
        except:
            pass

# ---------------- COMMANDS ----------------
@app.on_message(filters.command("start"))
async def start(_, message):
    await message.reply(
        "📤 Send me a video or file\n"
        "I will upload it to cloud and give you play/download buttons 🎬⬇️\n\n"
        "Commands:\n"
        "/myfiles - View all your uploaded files"
    )

@app.on_message(filters.command("myfiles"))
async def myfiles(_, message):
    user_id = str(message.from_user.id)
    
    try:
        # List all files in user's folder
        response = s3.list_objects_v2(
            Bucket=R2_BUCKET_NAME,
            Prefix=f"{user_id}/"
        )
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            await message.reply("📁 You haven't uploaded any files yet!")
            return
        
        files_text = "📁 **Your Uploaded Files:**\n\n"
        
        for obj in response['Contents']:
            file_key = obj['Key']
            file_name = file_key.replace(f"{user_id}/", "")
            file_size = obj['Size']
            file_url = f"{R2_PUBLIC_URL}/{file_key}"
            
            # Format file size
            size_str = human_bytes(file_size)
            
            files_text += f"📄 `{file_name}`\n"
            files_text += f"   Size: {size_str}\n"
            files_text += f"   [Download]({file_url})\n"
            files_text += f"   `/delete_file {file_name}`\n\n"
        
        await message.reply(files_text, disable_web_page_preview=True)
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("delete_file"))
async def delete_file(_, message):
    user_id = str(message.from_user.id)
    is_admin = user_id == str(ADMIN_ID)
    
    # Get filename and optional user_id from command
    try:
        if is_admin and len(message.command) == 3:
            # Admin format: /delete_file user_id filename
            target_user_id = message.command[1]
            file_name = message.command[2]
        else:
            # User format: /delete_file filename
            target_user_id = user_id
            file_name = message.command[1]
    except IndexError:
        if is_admin:
            await message.reply("❌ Usage:\nUser: `/delete_file filename.mp4`\nAdmin: `/delete_file user_id filename.mp4`")
        else:
            await message.reply("❌ Usage: `/delete_file filename.mp4`")
        return
    
    file_key = f"{target_user_id}/{file_name}"
    
    try:
        # Check if user is deleting their own file or is admin
        if target_user_id != user_id and not is_admin:
            await message.reply("❌ You can only delete your own files!")
            return
        
        # Check if file exists
        response = s3.list_objects_v2(
            Bucket=R2_BUCKET_NAME,
            Prefix=file_key
        )
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            await message.reply(f"❌ File '{file_name}' not found!")
            return
        
        # Delete the file
        s3.delete_object(Bucket=R2_BUCKET_NAME, Key=file_key)
        
        if is_admin and target_user_id != user_id:
            await message.reply(f"✅ File '{file_name}' from user {target_user_id} deleted successfully!")
        else:
            await message.reply(f"✅ File '{file_name}' deleted successfully!")
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("all_files"))
async def all_files(_, message):
    # Admin only
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ You don't have permission to use this command!")
        return
    
    try:
        # List all files in bucket
        response = s3.list_objects_v2(Bucket=R2_BUCKET_NAME)
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            await message.reply("📁 No files in storage!")
            return
        
        total_size = 0
        user_stats = {}
        
        # Calculate stats
        for obj in response['Contents']:
            file_key = obj['Key']
            file_size = obj['Size']
            total_size += file_size
            
            # Extract user ID from key
            user_id = file_key.split('/')[0]
            
            if user_id not in user_stats:
                user_stats[user_id] = {'count': 0, 'size': 0}
            
            user_stats[user_id]['count'] += 1
            user_stats[user_id]['size'] += file_size
        
        # Build response
        files_text = "📊 **All Files Statistics:**\n\n"
        files_text += f"💾 **Total Storage Used:** {human_bytes(total_size)}\n"
        files_text += f"👥 **Total Users:** {len(user_stats)}\n"
        files_text += f"📁 **Total Files:** {len(response['Contents'])}\n\n"
        
        files_text += "**Per User Breakdown:**\n\n"
        
        # Sort by size (largest first)
        sorted_users = sorted(user_stats.items(), key=lambda x: x[1]['size'], reverse=True)
        
        for user_id, stats in sorted_users:
            files_text += f"👤 User ID: `{user_id}`\n"
            files_text += f"   Files: {stats['count']}\n"
            files_text += f"   Storage: {human_bytes(stats['size'])}\n\n"
        
        await message.reply(files_text)
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("total_files"))
async def total_files(_, message):
    # Admin only
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ You don't have permission to use this command!")
        return
    
    try:
        # List all files in bucket
        response = s3.list_objects_v2(Bucket=R2_BUCKET_NAME)
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            await message.reply("📁 No files in storage!")
            return
        
        files_text = ""
        
        for obj in response['Contents']:
            file_key = obj['Key']
            file_name = file_key.split('/')[-1]
            file_size = obj['Size']
            user_id = file_key.split('/')[0]
            
            files_text += f"📁 File: `{file_name}`\n"
            files_text += f"💾 Size: {human_bytes(file_size)}\n"
            files_text += f"/delete_file {user_id} {file_name}\n\n"
        
        await message.reply(files_text)
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

# ---------------- MEDIA HANDLER ----------------
@app.on_message(filters.video | filters.document)
async def handle_media(_, message):
    media = message.video or message.document

    original_name = media.file_name or f"file_{message.id}.mp4"
    safe_name = original_name.replace(" ", "_")

    user_folder = str(message.from_user.id)
    r2_key = f"{user_folder}/{safe_name}"
    local_path = os.path.join(DOWNLOAD_DIR, safe_name)

    status_msg = await message.reply("🚀 Downloading...")

    start_time = time.time()

    # -------- DOWNLOAD --------
    await message.download(
        file_name=local_path,
        progress=progress,
        progress_args=(
            status_msg,
            start_time,
            "Downloading",
            safe_name
        )
    )

    file_size = os.path.getsize(local_path)

    # -------- UPLOAD --------
    upload_progress = UploadProgress(
        status_msg,
        safe_name,
        file_size
    )

    s3.upload_file(
        local_path,
        R2_BUCKET_NAME,
        r2_key,
        Callback=upload_progress,
        ExtraArgs={"ContentType": media.mime_type or "application/octet-stream"}
    )

    os.remove(local_path)

    public_link = f"{R2_PUBLIC_URL}/{r2_key}"

    # -------- INLINE BUTTONS --------
    worker_url = f"https://play-in-app.ftolbots.workers.dev/?url={public_link}"
    
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("▶️ Play In VLC", url=worker_url),
                InlineKeyboardButton("⬇️ Download", url=public_link),
            ],
        ]
    )

    response_text = (
        f"📁 Completed! File Name: `{safe_name}`\n"
        f"🎬 Play in -"
    )

    await status_msg.edit(
        response_text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

# ---------------- RUN ----------------
print("🤖 Bot is running...")
app.run()            f"📁 File Name: `{self.filename}`\n"
            f"👀 File Size: {human_bytes(self.filesize)}\n"
            f"⚡ Speed: {human_bytes(speed)}/s\n"
            f"⏳ ETA: {math.ceil(eta)} sec\n\n"
            f"`{bar}` {percent:.2f}%"
        )

        try:
            import asyncio
            asyncio.get_event_loop().create_task(
                self.msg.edit(text)
            )
        except:
            pass

# ---------------- COMMANDS ----------------
@app.on_message(filters.command("start"))
async def start(_, message):
    await message.reply(
        "📤 Send me a video or file\n"
        "I will upload it to cloud and give you play/download buttons 🎬⬇️\n\n"
        "Commands:\n"
        "/myfiles - View all your uploaded files"
    )

@app.on_message(filters.command("myfiles"))
async def myfiles(_, message):
    user_id = str(message.from_user.id)
    
    try:
        # List all files in user's folder
        response = s3.list_objects_v2(
            Bucket=R2_BUCKET_NAME,
            Prefix=f"{user_id}/"
        )
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            await message.reply("📁 You haven't uploaded any files yet!")
            return
        
        files_text = "📁 **Your Uploaded Files:**\n\n"
        
        for obj in response['Contents']:
            file_key = obj['Key']
            file_name = file_key.replace(f"{user_id}/", "")
            file_size = obj['Size']
            file_url = f"{R2_PUBLIC_URL}/{file_key}"
            
            # Format file size
            size_str = human_bytes(file_size)
            
            files_text += f"📄 `{file_name}`\n"
            files_text += f"   Size: {size_str}\n"
            files_text += f"   [Download]({file_url})\n"
            files_text += f"   `/delete_file {file_name}`\n\n"
        
        await message.reply(files_text, disable_web_page_preview=True)
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("delete_file"))
async def delete_file(_, message):
    user_id = str(message.from_user.id)
    is_admin = user_id == str(ADMIN_ID)
    
    # Get filename and optional user_id from command
    try:
        if is_admin and len(message.command) == 3:
            # Admin format: /delete_file user_id filename
            target_user_id = message.command[1]
            file_name = message.command[2]
        else:
            # User format: /delete_file filename
            target_user_id = user_id
            file_name = message.command[1]
    except IndexError:
        if is_admin:
            await message.reply("❌ Usage:\nUser: `/delete_file filename.mp4`\nAdmin: `/delete_file user_id filename.mp4`")
        else:
            await message.reply("❌ Usage: `/delete_file filename.mp4`")
        return
    
    file_key = f"{target_user_id}/{file_name}"
    
    try:
        # Check if user is deleting their own file or is admin
        if target_user_id != user_id and not is_admin:
            await message.reply("❌ You can only delete your own files!")
            return
        
        # Check if file exists
        response = s3.list_objects_v2(
            Bucket=R2_BUCKET_NAME,
            Prefix=file_key
        )
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            await message.reply(f"❌ File '{file_name}' not found!")
            return
        
        # Delete the file
        s3.delete_object(Bucket=R2_BUCKET_NAME, Key=file_key)
        
        if is_admin and target_user_id != user_id:
            await message.reply(f"✅ File '{file_name}' from user {target_user_id} deleted successfully!")
        else:
            await message.reply(f"✅ File '{file_name}' deleted successfully!")
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("all_files"))
async def all_files(_, message):
    # Admin only
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ You don't have permission to use this command!")
        return
    
    try:
        # List all files in bucket
        response = s3.list_objects_v2(Bucket=R2_BUCKET_NAME)
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            await message.reply("📁 No files in storage!")
            return
        
        total_size = 0
        user_stats = {}
        
        # Calculate stats
        for obj in response['Contents']:
            file_key = obj['Key']
            file_size = obj['Size']
            total_size += file_size
            
            # Extract user ID from key
            user_id = file_key.split('/')[0]
            
            if user_id not in user_stats:
                user_stats[user_id] = {'count': 0, 'size': 0}
            
            user_stats[user_id]['count'] += 1
            user_stats[user_id]['size'] += file_size
        
        # Build response
        files_text = "📊 **All Files Statistics:**\n\n"
        files_text += f"💾 **Total Storage Used:** {human_bytes(total_size)}\n"
        files_text += f"👥 **Total Users:** {len(user_stats)}\n"
        files_text += f"📁 **Total Files:** {len(response['Contents'])}\n\n"
        
        files_text += "**Per User Breakdown:**\n\n"
        
        # Sort by size (largest first)
        sorted_users = sorted(user_stats.items(), key=lambda x: x[1]['size'], reverse=True)
        
        for user_id, stats in sorted_users:
            files_text += f"👤 User ID: `{user_id}`\n"
            files_text += f"   Files: {stats['count']}\n"
            files_text += f"   Storage: {human_bytes(stats['size'])}\n\n"
        
        await message.reply(files_text)
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

@app.on_message(filters.command("total_files"))
async def total_files(_, message):
    # Admin only
    if message.from_user.id != ADMIN_ID:
        await message.reply("❌ You don't have permission to use this command!")
        return
    
    try:
        # List all files in bucket
        response = s3.list_objects_v2(Bucket=R2_BUCKET_NAME)
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            await message.reply("📁 No files in storage!")
            return
        
        files_text = ""
        
        for obj in response['Contents']:
            file_key = obj['Key']
            file_name = file_key.split('/')[-1]
            file_size = obj['Size']
            user_id = file_key.split('/')[0]
            
            files_text += f"📁 File: `{file_name}`\n"
            files_text += f"💾 Size: {human_bytes(file_size)}\n"
            files_text += f"/delete_file {user_id} {file_name}\n\n"
        
        await message.reply(files_text)
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

# ---------------- MEDIA HANDLER ----------------
@app.on_message(filters.video | filters.document)
async def handle_media(_, message):
    media = message.video or message.document

    original_name = media.file_name or f"file_{message.id}.mp4"
    safe_name = original_name.replace(" ", "_")

    user_folder = str(message.from_user.id)
    r2_key = f"{user_folder}/{safe_name}"
    local_path = os.path.join(DOWNLOAD_DIR, safe_name)

    status_msg = await message.reply("🚀 Downloading...")

    start_time = time.time()

    # -------- DOWNLOAD --------
    await message.download(
        file_name=local_path,
        progress=progress,
        progress_args=(
            status_msg,
            start_time,
            "Downloading",
            safe_name
        )
    )

    file_size = os.path.getsize(local_path)

    # -------- UPLOAD --------
    upload_progress = UploadProgress(
        status_msg,
        safe_name,
        file_size
    )

    s3.upload_file(
        local_path,
        R2_BUCKET_NAME,
        r2_key,
        Callback=upload_progress,
        ExtraArgs={"ContentType": media.mime_type or "application/octet-stream"}
    )

    os.remove(local_path)

    public_link = f"{R2_PUBLIC_URL}/{r2_key}"

    # -------- INLINE BUTTONS --------
    worker_url = f"https://play-in-app.ftolbots.workers.dev/?url={public_link}"
    
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("▶️ Play In VLC", url=worker_url),
                InlineKeyboardButton("⬇️ Download", url=public_link),
            ],
        ]
    )

    response_text = (
        f"📁 Completed! File Name: `{safe_name}`\n"
        f"🎬 Play in -"
    )

    await status_msg.edit(
        response_text,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

# ---------------- RUN ----------------
print("🤖 Bot is running...")
app.run()

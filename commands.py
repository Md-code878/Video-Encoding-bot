from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from config import Config
from database import db

# ── Decorators ───────────────────────────────────────────────────────


def admin_only(func):
    async def wrapper(client: Client, message: Message):
        if message.from_user.id not in Config.ADMIN_IDS:
            await message.reply_text("⛔ This command is admin-only.")
            return
        return await func(client, message)
    wrapper.__name__ = func.__name__
    return wrapper


def check_ban(func):
    async def wrapper(client: Client, message: Message):
        if await db.is_banned(message.from_user.id):
            await message.reply_text("🚫 You are banned from using this bot.")
            return
        return await func(client, message)
    wrapper.__name__ = func.__name__
    return wrapper


# ── Public Commands ──────────────────────────────────────────────────


def register_commands(app: Client):

    @app.on_message(filters.command("start") & filters.private)
    @check_ban
    async def start_cmd(client: Client, message: Message):
        user = message.from_user
        await db.add_user(user.id, user.username or user.first_name)

        await message.reply_text(
            f"👋 **Hello {user.first_name}!**\n\n"
            "I'm a **Video Encoder & Upscaler Bot** powered by FFmpeg.\n\n"
            "**What I can do:**\n"
            "• Encode video to **H.264**, **H.265 (HEVC)**, or **AV1**\n"
            "• Upscale video to **1080p / 2K / 4K / 8K**\n"
            "• 🚀 **GPU acceleration** on NVIDIA (Google Colab)\n\n"
            "**How to use:**\n"
            "1️⃣ Send me a video file\n"
            "2️⃣ Choose codec & resolution\n"
            "3️⃣ Wait for processing\n"
            "4️⃣ Get your encoded file!\n\n"
            "Use /help for all commands.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📖 Help", callback_data="help"),
                 InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
                [InlineKeyboardButton("📊 Stats", callback_data="stats")],
            ]),
        )

    @app.on_message(filters.command("help") & filters.private)
    @check_ban
    async def help_cmd(client: Client, message: Message):
        await message.reply_text(
            "📖 **Commands**\n\n"
            "**User Commands:**\n"
            "/start — Start the bot\n"
            "/help — Show this help\n"
            "/encode — Encode a video (reply to video)\n"
            "/upscale — Upscale a video (reply to video)\n"
            "/settings — Your encoding preferences\n"
            "/stats — Bot statistics\n"
            "/mediainfo — Get video info (reply to video)\n\n"
            "**Admin Commands:**\n"
            "/ban `<user_id>` — Ban a user\n"
            "/unban `<user_id>` — Unban a user\n"
            "/broadcast `<message>` — Broadcast to all users\n"
            "/status — Bot system status\n"
            "/logs — Get recent logs\n"
        )

    @app.on_message(filters.command("settings") & filters.private)
    @check_ban
    async def settings_cmd(client: Client, message: Message):
        user = message.from_user
        await db.add_user(user.id, user.username or "")
        user_data = await db.get_user(user.id)

        codec = user_data.get("default_codec", "hevc") if user_data else "hevc"
        res = user_data.get("default_resolution", "None") if user_data else "None"

        await message.reply_text(
            "⚙️ **Your Settings**\n\n"
            f"**Default Codec:** `{codec.upper()}`\n"
            f"**Default Resolution:** `{res or 'Original'}`\n\n"
            "Tap below to change:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Change Codec", callback_data="set_codec")],
                [InlineKeyboardButton("📐 Change Resolution", callback_data="set_res")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_start")],
            ]),
        )

    @app.on_message(filters.command("stats") & filters.private)
    @check_ban
    async def stats_cmd(client: Client, message: Message):
        total_users = await db.total_users()
        total_tasks = await db.total_tasks()
        user = await db.get_user(message.from_user.id)
        my_tasks = user.get("tasks_completed", 0) if user else 0

        await message.reply_text(
            "📊 **Bot Statistics**\n\n"
            f"👥 **Total Users:** {total_users}\n"
            f"🎬 **Total Encodes:** {total_tasks}\n"
            f"📁 **Your Encodes:** {my_tasks}\n"
        )

    @app.on_message(filters.command("mediainfo") & filters.private)
    @check_ban
    async def mediainfo_cmd(client: Client, message: Message):
        from utils.encoder import probe_video
        from utils.helpers import humanbytes
        import os

        reply = message.reply_to_message
        if not reply or not (reply.video or reply.document):
            await message.reply_text("↩️ Reply to a video file with /mediainfo")
            return

        status_msg = await message.reply_text("🔍 Analyzing video...")

        try:
            filepath = await reply.download(file_name=os.path.join(Config.TEMP_DIR, "probe_"))
            info = await probe_video(filepath)
            os.remove(filepath)

            if not info:
                await status_msg.edit_text("❌ Could not read video metadata.")
                return

            await status_msg.edit_text(
                "🎬 **Media Info**\n\n"
                f"**Resolution:** {info['width']}×{info['height']}\n"
                f"**Codec:** {info['codec']}\n"
                f"**FPS:** {info['fps']}\n"
                f"**Duration:** {int(info['duration'])}s\n"
                f"**Bitrate:** {humanbytes(info['bitrate'])}/s\n"
                f"**Size:** {humanbytes(info['size'])}\n"
            )
        except Exception as e:
            await status_msg.edit_text(f"❌ Error: {e}")

    # ── Admin Commands ───────────────────────────────────────────────

    @app.on_message(filters.command("ban") & filters.private)
    @admin_only
    async def ban_cmd(client: Client, message: Message):
        if len(message.command) < 2:
            await message.reply_text("Usage: /ban <user_id>")
            return
        try:
            uid = int(message.command[1])
            await db.ban_user(uid)
            await message.reply_text(f"✅ User `{uid}` banned.")
        except ValueError:
            await message.reply_text("❌ Invalid user ID.")

    @app.on_message(filters.command("unban") & filters.private)
    @admin_only
    async def unban_cmd(client: Client, message: Message):
        if len(message.command) < 2:
            await message.reply_text("Usage: /unban <user_id>")
            return
        try:
            uid = int(message.command[1])
            await db.unban_user(uid)
            await message.reply_text(f"✅ User `{uid}` unbanned.")
        except ValueError:
            await message.reply_text("❌ Invalid user ID.")

    @app.on_message(filters.command("broadcast") & filters.private)
    @admin_only
    async def broadcast_cmd(client: Client, message: Message):
        if len(message.command) < 2:
            await message.reply_text("Usage: /broadcast <message>")
            return

        text = message.text.split(None, 1)[1]
        users = await db.get_all_users()
        sent, failed = 0, 0

        status_msg = await message.reply_text("📡 Broadcasting...")

        for user in users:
            try:
                await client.send_message(user["user_id"], text)
                sent += 1
            except Exception:
                failed += 1

        await status_msg.edit_text(
            f"📡 **Broadcast Complete**\n\n✅ Sent: {sent}\n❌ Failed: {failed}"
        )

    @app.on_message(filters.command("status") & filters.private)
    @admin_only
    async def status_cmd(client: Client, message: Message):
        import psutil
        import shutil

        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        disk = shutil.disk_usage("/")
        from utils.helpers import humanbytes
        from utils.gpu import get_cached_gpu_info, detect_gpu

        gpu_info = get_cached_gpu_info()
        if gpu_info is None:
            gpu_info = await detect_gpu()

        if gpu_info["available"]:
            gpu_text = (
                f"🚀 **GPU:** {gpu_info['gpu_name']}\n"
                f"**NVENC:** {', '.join(gpu_info['nvenc_encoders'])}\n"
            )
        else:
            gpu_text = "⚙️ **GPU:** Not detected (CPU mode)\n"

        await message.reply_text(
            "🖥️ **System Status**\n\n"
            f"**CPU:** {cpu}%\n"
            f"**RAM:** {humanbytes(mem.used)} / {humanbytes(mem.total)} ({mem.percent}%)\n"
            f"**Disk:** {humanbytes(disk.used)} / {humanbytes(disk.total)}\n"
            f"**Workers:** {Config.MAX_WORKERS}\n\n"
            f"{gpu_text}"
        )

    @app.on_message(filters.command("logs") & filters.private)
    @admin_only
    async def logs_cmd(client: Client, message: Message):
        import os
        log_file = "bot.log"
        if not os.path.exists(log_file):
            await message.reply_text("No log file found.")
            return
        # Send last 50 lines
        with open(log_file, "r") as f:
            lines = f.readlines()[-50:]
        text = "".join(lines)
        if len(text) > 4000:
            text = text[-4000:]
        await message.reply_text(f"📋 **Recent Logs:**\n```\n{text}\n```")

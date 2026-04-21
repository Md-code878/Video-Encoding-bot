from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from database import db


def register_callbacks(app: Client):

    @app.on_callback_query(filters.regex(r"^help$"))
    async def help_cb(client: Client, query: CallbackQuery):
        await query.message.edit_text(
            "📖 **Commands**\n\n"
            "/encode — Encode a video (reply to video)\n"
            "/upscale — Upscale a video (reply to video)\n"
            "/settings — Your encoding preferences\n"
            "/stats — Bot statistics\n"
            "/mediainfo — Get video info (reply to video)\n",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="back_start")],
            ]),
        )

    @app.on_callback_query(filters.regex(r"^stats$"))
    async def stats_cb(client: Client, query: CallbackQuery):
        total_users = await db.total_users()
        total_tasks = await db.total_tasks()
        user = await db.get_user(query.from_user.id)
        my_tasks = user.get("tasks_completed", 0) if user else 0

        await query.message.edit_text(
            "📊 **Bot Statistics**\n\n"
            f"👥 **Total Users:** {total_users}\n"
            f"🎬 **Total Encodes:** {total_tasks}\n"
            f"📁 **Your Encodes:** {my_tasks}\n",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="back_start")],
            ]),
        )

    @app.on_callback_query(filters.regex(r"^back_start$"))
    async def back_start_cb(client: Client, query: CallbackQuery):
        await query.message.edit_text(
            f"👋 **Hello {query.from_user.first_name}!**\n\n"
            "Send me a video file to encode or upscale!\n\n"
            "Use /help for all commands.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📖 Help", callback_data="help"),
                 InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
                [InlineKeyboardButton("📊 Stats", callback_data="stats")],
            ]),
        )

    @app.on_callback_query(filters.regex(r"^settings$"))
    async def settings_cb(client: Client, query: CallbackQuery):
        user_data = await db.get_user(query.from_user.id)
        codec = user_data.get("default_codec", "hevc") if user_data else "hevc"
        res = user_data.get("default_resolution") if user_data else None

        await query.message.edit_text(
            "⚙️ **Your Settings**\n\n"
            f"**Default Codec:** `{codec.upper()}`\n"
            f"**Default Resolution:** `{res or 'Original'}`\n",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Change Codec", callback_data="set_codec")],
                [InlineKeyboardButton("📐 Change Resolution", callback_data="set_res")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_start")],
            ]),
        )

    # ── Codec Selection ──────────────────────────────────────────────

    @app.on_callback_query(filters.regex(r"^set_codec$"))
    async def set_codec_cb(client: Client, query: CallbackQuery):
        await query.message.edit_text(
            "🔄 **Select Default Codec:**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("H.264", callback_data="codec_h264"),
                 InlineKeyboardButton("H.265 (HEVC)", callback_data="codec_hevc")],
                [InlineKeyboardButton("AV1", callback_data="codec_av1")],
                [InlineKeyboardButton("🔙 Back", callback_data="settings")],
            ]),
        )

    @app.on_callback_query(filters.regex(r"^codec_(h264|hevc|av1)$"))
    async def codec_select_cb(client: Client, query: CallbackQuery):
        codec = query.data.split("_")[1]
        await db.set_user_codec(query.from_user.id, codec)
        await query.answer(f"✅ Default codec set to {codec.upper()}")
        # Return to settings
        user_data = await db.get_user(query.from_user.id)
        res = user_data.get("default_resolution") if user_data else None
        await query.message.edit_text(
            "⚙️ **Your Settings**\n\n"
            f"**Default Codec:** `{codec.upper()}`\n"
            f"**Default Resolution:** `{res or 'Original'}`\n",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Change Codec", callback_data="set_codec")],
                [InlineKeyboardButton("📐 Change Resolution", callback_data="set_res")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_start")],
            ]),
        )

    # ── Resolution Selection ─────────────────────────────────────────

    @app.on_callback_query(filters.regex(r"^set_res$"))
    async def set_res_cb(client: Client, query: CallbackQuery):
        await query.message.edit_text(
            "📐 **Select Default Upscale Resolution:**\n\n"
            "Choose 'Original' to keep the source resolution.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Original", callback_data="res_none")],
                [InlineKeyboardButton("1080p", callback_data="res_1080p"),
                 InlineKeyboardButton("2K", callback_data="res_2k")],
                [InlineKeyboardButton("4K", callback_data="res_4k"),
                 InlineKeyboardButton("8K", callback_data="res_8k")],
                [InlineKeyboardButton("🔙 Back", callback_data="settings")],
            ]),
        )

    @app.on_callback_query(filters.regex(r"^res_(none|1080p|2k|4k|8k)$"))
    async def res_select_cb(client: Client, query: CallbackQuery):
        res = query.data.split("_", 1)[1]
        if res == "none":
            res = None
        await db.set_user_resolution(query.from_user.id, res)
        label = res.upper() if res else "Original"
        await query.answer(f"✅ Default resolution set to {label}")
        # Return to settings
        user_data = await db.get_user(query.from_user.id)
        codec = user_data.get("default_codec", "hevc") if user_data else "hevc"
        await query.message.edit_text(
            "⚙️ **Your Settings**\n\n"
            f"**Default Codec:** `{codec.upper()}`\n"
            f"**Default Resolution:** `{label}`\n",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Change Codec", callback_data="set_codec")],
                [InlineKeyboardButton("📐 Change Resolution", callback_data="set_res")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_start")],
            ]),
        )

    # ── Encode/Upscale Callbacks (from video handler) ────────────────

    @app.on_callback_query(filters.regex(r"^enc_(h264|hevc|av1)_(none|1080p|2k|4k|8k)$"))
    async def encode_cb(client: Client, query: CallbackQuery):
        """Triggered when user picks codec + resolution from video handler."""
        parts = query.data.split("_")
        codec = parts[1]
        resolution = parts[2] if parts[2] != "none" else None

        # Store choice in user's context and trigger encoding
        from plugins.video_handler import start_encode
        await start_encode(client, query, codec, resolution)

    @app.on_callback_query(filters.regex(r"^cancel_encode$"))
    async def cancel_encode_cb(client: Client, query: CallbackQuery):
        await query.message.edit_text("❌ Encoding cancelled.")
        await query.answer("Cancelled")

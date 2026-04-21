import asyncio
import os
import time
import logging
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import Config
from database import db
from utils.encoder import encode_video, probe_video
from utils.gpu import detect_gpu, get_cached_gpu_info
from utils.helpers import humanbytes, time_formatter

logger = logging.getLogger(__name__)

# Active encoding tasks: {user_id: asyncio.Task}
_active_tasks: dict[int, asyncio.Task] = {}
# Semaphore to limit concurrent workers
_worker_sem = asyncio.Semaphore(Config.MAX_WORKERS)

# Store pending video message IDs for encode callback
_pending_videos: dict[int, Message] = {}


def register_video_handler(app: Client):

    @app.on_message(
        filters.private
        & (filters.video | filters.document)
    )
    async def on_video(client: Client, message: Message):
        user = message.from_user

        # Check ban
        if await db.is_banned(user.id):
            return

        await db.add_user(user.id, user.username or user.first_name)

        # Validate it's a video
        media = message.video or message.document
        if message.document and not (
            message.document.mime_type and message.document.mime_type.startswith("video/")
        ):
            return

        # Check file size
        if media.file_size and media.file_size > Config.MAX_FILE_SIZE:
            await message.reply_text(
                f"❌ File too large. Max: {humanbytes(Config.MAX_FILE_SIZE)}"
            )
            return

        # Check if user already has an active task
        if user.id in _active_tasks and not _active_tasks[user.id].done():
            await message.reply_text(
                "⏳ You already have an active encode. Wait for it to finish or /cancel."
            )
            return

        # Store the video message for the callback
        _pending_videos[user.id] = message

        # Get user defaults
        user_data = await db.get_user(user.id)
        default_codec = user_data.get("default_codec", "hevc") if user_data else "hevc"

        file_info = f"📁 **{media.file_name or 'video'}**\n" f"📦 **Size:** {humanbytes(media.file_size or 0)}\n"

        if message.video:
            file_info += (
                f"📐 **Resolution:** {message.video.width}×{message.video.height}\n"
                f"⏱ **Duration:** {time_formatter(message.video.duration or 0)}\n"
            )

        await message.reply_text(
            f"🎬 **Video Received!**\n\n{file_info}\n"
            "**Choose encoding options:**\n\n"
            "First, select **codec**:",
            reply_markup=_codec_keyboard(),
        )

    @app.on_callback_query(filters.regex(r"^pick_codec_(h264|hevc|av1)$"))
    async def pick_codec_cb(client: Client, query: CallbackQuery):
        codec = query.data.split("_")[-1]
        codec_cfg = Config.CODECS.get(codec, {})
        label = codec_cfg.get("label", codec.upper())
        await query.message.edit_text(
            f"**Codec:** `{label}`\n\n"
            "Now select **resolution**:\n"
            "_(Choose 'Original' to keep source resolution)_",
            reply_markup=_resolution_keyboard(codec),
        )

    @app.on_callback_query(filters.regex(r"^pick_res_(h264|hevc|av1)_(none|1080p|2k|4k|8k)$"))
    async def pick_res_cb(client: Client, query: CallbackQuery):
        parts = query.data.split("_")
        codec = parts[2]
        resolution = parts[3] if parts[3] != "none" else None
        await start_encode(client, query, codec, resolution)

    @app.on_message(filters.command("encode") & filters.private)
    async def encode_cmd(client: Client, message: Message):
        reply = message.reply_to_message
        if not reply or not (reply.video or reply.document):
            await message.reply_text("↩️ Reply to a video with /encode")
            return

        _pending_videos[message.from_user.id] = reply
        await message.reply_text(
            "**Select codec for encoding:**",
            reply_markup=_codec_keyboard(),
        )

    @app.on_message(filters.command("upscale") & filters.private)
    async def upscale_cmd(client: Client, message: Message):
        reply = message.reply_to_message
        if not reply or not (reply.video or reply.document):
            await message.reply_text("↩️ Reply to a video with /upscale")
            return

        _pending_videos[message.from_user.id] = reply
        user_data = await db.get_user(message.from_user.id)
        default_codec = user_data.get("default_codec", "hevc") if user_data else "hevc"

        await message.reply_text(
            "**Select upscale resolution:**\n\n"
            f"_(Codec: {default_codec.upper()} — change in /settings)_",
            reply_markup=_resolution_keyboard(default_codec),
        )

    @app.on_message(filters.command("cancel") & filters.private)
    async def cancel_cmd(client: Client, message: Message):
        uid = message.from_user.id
        if uid in _active_tasks and not _active_tasks[uid].done():
            _active_tasks[uid].cancel()
            del _active_tasks[uid]
            await message.reply_text("✅ Encoding cancelled.")
        else:
            await message.reply_text("No active encoding to cancel.")


async def start_encode(
    client: Client,
    query: CallbackQuery,
    codec: str,
    resolution: str | None,
):
    """Start the download → encode → upload pipeline."""
    user_id = query.from_user.id
    video_msg = _pending_videos.pop(user_id, None)

    if not video_msg:
        await query.message.edit_text("❌ Video message expired. Please send the video again.")
        return

    res_label = resolution.upper() if resolution else "Original"
    codec_cfg = Config.CODECS.get(codec, {})
    codec_label = codec_cfg.get("label", codec.upper())

    # Show GPU status
    gpu_info = get_cached_gpu_info()
    if gpu_info and gpu_info["available"]:
        hw_badge = f"🚀 GPU: {gpu_info['gpu_name']}"
    else:
        hw_badge = "⚙️ CPU mode"

    await query.message.edit_text(
        f"✅ **Encoding started!**\n\n"
        f"**Codec:** {codec_label}\n"
        f"**Resolution:** {res_label}\n"
        f"**Engine:** {hw_badge}\n"
        f"⏳ Downloading..."
    )

    task = asyncio.create_task(
        _encode_pipeline(client, query, video_msg, codec, resolution)
    )
    _active_tasks[user_id] = task


async def _encode_pipeline(
    client: Client,
    query: CallbackQuery,
    video_msg: Message,
    codec: str,
    resolution: str | None,
):
    """Full pipeline: download → probe → encode → upload → cleanup."""
    user_id = query.from_user.id
    status_msg = query.message
    start_time = time.time()

    os.makedirs(Config.TEMP_DIR, exist_ok=True)
    input_path = None
    output_path = None

    try:
        # ── Download ─────────────────────────────────────────────────
        dl_start = time.time()
        input_path = await video_msg.download(
            file_name=os.path.join(Config.TEMP_DIR, f"{user_id}_{int(time.time())}_input"),
            progress=lambda c, t: _dl_progress(c, t, status_msg, dl_start),
        )

        if not input_path or not os.path.exists(input_path):
            await status_msg.edit_text("❌ Download failed.")
            return

        # ── Probe ────────────────────────────────────────────────────
        info = await probe_video(input_path)
        if not info:
            await status_msg.edit_text("❌ Cannot read video file.")
            return

        input_size = os.path.getsize(input_path)
        # Detect GPU for this encode
        gpu_info = await detect_gpu()
        if gpu_info["available"]:
            hw_badge = f"🚀 GPU ({gpu_info['gpu_name']})"
        else:
            hw_badge = "⚙️ CPU"

        codec_cfg = Config.CODECS.get(codec, {})
        codec_label = codec_cfg.get("label", codec.upper())

        await status_msg.edit_text(
            f"📥 Downloaded: {humanbytes(input_size)}\n"
            f"📐 Source: {info['width']}×{info['height']} ({info['codec']})\n"
            f"⏱ Duration: {time_formatter(info['duration'])}\n\n"
            f"🔄 **Encoding to {codec_label}...**\n"
            f"Resolution: {resolution.upper() if resolution else 'Original'}\n"
            f"Engine: {hw_badge}\n\n"
            f"`[░░░░░░░░░░░░]` 0%"
        )

        # ── Encode ───────────────────────────────────────────────────
        codec_cfg = Config.CODECS[codec]
        ext = codec_cfg["ext"]
        output_path = os.path.join(
            Config.TEMP_DIR, f"{user_id}_{int(time.time())}_output.{ext}"
        )

        last_update = [0.0]

        async def enc_progress(pct: float, elapsed: float):
            now = time.time()
            if now - last_update[0] < 8:
                return
            last_update[0] = now

            bar_len = 12
            filled = int(bar_len * pct / 100)
            bar = "█" * filled + "░" * (bar_len - filled)

            try:
                await status_msg.edit_text(
                    f"🔄 **Encoding to {codec_label}...**\n"
                    f"Engine: {hw_badge}\n\n"
                    f"`[{bar}]` {pct:.1f}%\n"
                    f"⏱ Elapsed: {time_formatter(elapsed)}"
                )
            except Exception:
                pass

        async with _worker_sem:
            success, msg = await encode_video(
                input_path, output_path, codec, resolution, enc_progress
            )

        if not success:
            await status_msg.edit_text(f"❌ Encoding failed:\n`{msg}`")
            return

        output_size = os.path.getsize(output_path)
        elapsed = time.time() - start_time

        await status_msg.edit_text(
            f"✅ **Encoding complete!**\n\n"
            f"📦 Input: {humanbytes(input_size)} → Output: {humanbytes(output_size)}\n"
            f"⏱ Time: {time_formatter(elapsed)}\n\n"
            f"📤 **Uploading...**"
        )

        # ── Upload ───────────────────────────────────────────────────
        ul_start = time.time()

        media = video_msg.video or video_msg.document
        filename = f"encoded_{codec}_{resolution or 'orig'}_{media.file_name or 'video'}"
        if not filename.endswith(f".{ext}"):
            filename = f"{os.path.splitext(filename)[0]}.{ext}"

        # Check upload size limit (2GB for Telegram)
        if output_size > 2 * 1024 * 1024 * 1024:
            await status_msg.edit_text(
                f"❌ Output file ({humanbytes(output_size)}) exceeds Telegram's 2GB upload limit."
            )
            return

        caption = (
            f"✅ **Encoded Video**\n\n"
            f"**Codec:** {codec.upper()}\n"
            f"**Resolution:** {resolution.upper() if resolution else 'Original'}\n"
            f"**Size:** {humanbytes(input_size)} → {humanbytes(output_size)}\n"
            f"**Time:** {time_formatter(elapsed)}"
        )

        await client.send_document(
            chat_id=query.from_user.id,
            document=output_path,
            file_name=filename,
            caption=caption,
            progress=lambda c, t: _ul_progress(c, t, status_msg, ul_start),
        )

        total_time = time.time() - start_time
        await status_msg.edit_text(
            f"✅ **Done!**\n\n"
            f"**Codec:** {codec.upper()}\n"
            f"**Resolution:** {resolution.upper() if resolution else 'Original'}\n"
            f"📦 {humanbytes(input_size)} → {humanbytes(output_size)}\n"
            f"⏱ Total: {time_formatter(total_time)}"
        )

        # ── Log & DB ────────────────────────────────────────────────
        await db.increment_tasks(user_id)
        await db.add_task({
            "user_id": user_id,
            "codec": codec,
            "resolution": resolution,
            "input_size": input_size,
            "output_size": output_size,
            "duration": info["duration"],
            "elapsed": total_time,
            "status": "completed",
            "timestamp": datetime.utcnow(),
        })

        # Log to channel
        if Config.LOG_CHANNEL:
            try:
                await client.send_message(
                    Config.LOG_CHANNEL,
                    f"✅ **Encode Complete**\n"
                    f"User: `{user_id}`\n"
                    f"Codec: {codec.upper()}\n"
                    f"Res: {resolution or 'Original'}\n"
                    f"Size: {humanbytes(input_size)} → {humanbytes(output_size)}\n"
                    f"Time: {time_formatter(total_time)}",
                )
            except Exception:
                pass

    except asyncio.CancelledError:
        await status_msg.edit_text("❌ Encoding cancelled.")
        logger.info(f"Encoding cancelled for user {user_id}")
    except Exception as e:
        logger.exception(f"Encoding error for user {user_id}")
        await status_msg.edit_text(f"❌ Error: `{e}`")
    finally:
        # Cleanup temp files
        for path in [input_path, output_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        _active_tasks.pop(user_id, None)


async def _dl_progress(current, total, message, start_time):
    """Throttled download progress updater."""
    now = time.time()
    key = f"dl_{message.chat.id}_{message.id}"
    if not hasattr(_dl_progress, "_ts"):
        _dl_progress._ts = {}
    if now - _dl_progress._ts.get(key, 0) < 5:
        return
    _dl_progress._ts[key] = now

    pct = current / total * 100 if total else 0
    elapsed = now - start_time
    speed = current / elapsed if elapsed > 0 else 0

    try:
        await message.edit_text(
            f"📥 **Downloading...**\n\n"
            f"{humanbytes(current)} / {humanbytes(total)} ({pct:.1f}%)\n"
            f"Speed: {humanbytes(speed)}/s"
        )
    except Exception:
        pass


async def _ul_progress(current, total, message, start_time):
    """Throttled upload progress updater."""
    now = time.time()
    key = f"ul_{message.chat.id}_{message.id}"
    if not hasattr(_ul_progress, "_ts"):
        _ul_progress._ts = {}
    if now - _ul_progress._ts.get(key, 0) < 5:
        return
    _ul_progress._ts[key] = now

    pct = current / total * 100 if total else 0
    elapsed = now - start_time
    speed = current / elapsed if elapsed > 0 else 0

    try:
        await message.edit_text(
            f"📤 **Uploading...**\n\n"
            f"{humanbytes(current)} / {humanbytes(total)} ({pct:.1f}%)\n"
            f"Speed: {humanbytes(speed)}/s"
        )
    except Exception:
        pass


def _codec_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("H.264", callback_data="pick_codec_h264"),
            InlineKeyboardButton("H.265 (HEVC)", callback_data="pick_codec_hevc"),
        ],
        [
            InlineKeyboardButton("AV1", callback_data="pick_codec_av1"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_encode")],
    ])


def _resolution_keyboard(codec: str):
    # Show GPU badge in resolution selection
    gpu_info = get_cached_gpu_info()
    gpu_note = ""
    if gpu_info and gpu_info["available"]:
        gpu_note = f"\n🚀 GPU acceleration active ({gpu_info['gpu_name']})"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Original", callback_data=f"pick_res_{codec}_none")],
        [
            InlineKeyboardButton("1080p", callback_data=f"pick_res_{codec}_1080p"),
            InlineKeyboardButton("2K", callback_data=f"pick_res_{codec}_2k"),
        ],
        [
            InlineKeyboardButton("4K", callback_data=f"pick_res_{codec}_4k"),
            InlineKeyboardButton("8K", callback_data=f"pick_res_{codec}_8k"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_encode")],
    ])

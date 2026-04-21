#!/usr/bin/env python3
"""
Telegram Video Encoder & Upscaler Bot
Encode videos to AV1/HEVC and upscale to 1080p/2K/4K/8K using FFmpeg.
"""

import asyncio
import os
import logging
from pyrogram import Client

from config import Config
from commands import register_commands
from plugins.callbacks import register_callbacks
from plugins.video_handler import register_video_handler
from utils.gpu import detect_gpu

# ── Logging ──────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ── Create temp directory ────────────────────────────────────────────
os.makedirs(Config.TEMP_DIR, exist_ok=True)

# ── Initialize Pyrogram Client ───────────────────────────────────────

app = Client(
    name="VideoEncoderBot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    workers=Config.MAX_WORKERS + 4,  # extra workers for commands/callbacks
)

# ── Register Handlers ────────────────────────────────────────────────

register_commands(app)
register_callbacks(app)
register_video_handler(app)

# ── Start ────────────────────────────────────────────────────────────

async def _startup_gpu_check():
    """Detect GPU at startup and log results."""
    gpu = await detect_gpu()
    if gpu["available"]:
        logger.info(f"🚀 GPU detected: {gpu['gpu_name']}")
        logger.info(f"🚀 NVENC encoders: {gpu['nvenc_encoders']}")
    else:
        logger.info("⚙️ No GPU detected — using CPU encoders")


if __name__ == "__main__":
    logger.info("Starting Video Encoder Bot...")
    logger.info(f"Admins: {Config.ADMIN_IDS}")
    logger.info(f"Max workers: {Config.MAX_WORKERS}")
    logger.info(f"Temp dir: {Config.TEMP_DIR}")
    logger.info(f"Available codecs: {list(Config.CODECS.keys())}")
    logger.info(f"Available resolutions: {list(Config.RESOLUTIONS.keys())}")

    # Detect GPU before starting
    asyncio.get_event_loop().run_until_complete(_startup_gpu_check())

    app.run()

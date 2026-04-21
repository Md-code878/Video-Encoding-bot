import os
from dotenv import load_dotenv

load_dotenv("config.env")


class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    API_ID = int(os.getenv("API_ID", "0"))
    API_HASH = os.getenv("API_HASH", "")

    ADMIN_IDS = [
        int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
    ]

    MONGO_URI = os.getenv("MONGO_URI", "")
    DB_NAME = os.getenv("DB_NAME", "videoencoderbot")

    LOG_CHANNEL = int(os.getenv("LOG_CHANNEL", "0"))

    FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
    FFPROBE_PATH = os.getenv("FFPROBE_PATH", "ffprobe")

    MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 2147483648))
    MAX_WORKERS = int(os.getenv("MAX_WORKERS", 2))
    TEMP_DIR = os.getenv("TEMP_DIR", "./downloads")

    # Encoding presets
    RESOLUTIONS = {
        "1080p": (1920, 1080),
        "2k": (2560, 1440),
        "4k": (3840, 2160),
        "8k": (7680, 4320),
    }

    # ── Codec Definitions ────────────────────────────────────────────
    # Each codec has a "gpu" variant (NVENC) and a "cpu" fallback.
    # The encoder picks GPU if available, otherwise falls back to CPU.

    CODECS = {
        "h264": {
            "gpu": {
                "encoder": "h264_nvenc",
                "params": [
                    "-preset", "p4",       # balanced speed/quality
                    "-rc", "vbr",
                    "-cq", "24",
                    "-b:v", "0",
                    "-pix_fmt", "yuv420p",
                ],
            },
            "cpu": {
                "encoder": "libx264",
                "params": ["-crf", "23", "-preset", "medium", "-pix_fmt", "yuv420p"],
            },
            "ext": "mkv",
            "label": "H.264",
        },
        "hevc": {
            "gpu": {
                "encoder": "hevc_nvenc",
                "params": [
                    "-preset", "p4",
                    "-rc", "vbr",
                    "-cq", "26",
                    "-b:v", "0",
                    "-pix_fmt", "p010le",  # 10-bit
                ],
            },
            "cpu": {
                "encoder": "libx265",
                "params": ["-crf", "24", "-preset", "medium", "-pix_fmt", "yuv420p10le"],
            },
            "ext": "mkv",
            "label": "H.265 (HEVC)",
        },
        "av1": {
            "gpu": {
                "encoder": "av1_nvenc",
                "params": [
                    "-preset", "p4",
                    "-rc", "vbr",
                    "-cq", "30",
                    "-b:v", "0",
                    "-pix_fmt", "p010le",
                ],
            },
            "cpu": {
                "encoder": "libsvtav1",
                "params": ["-crf", "30", "-preset", "6", "-pix_fmt", "yuv420p10le"],
            },
            "ext": "mkv",
            "label": "AV1",
        },
    }

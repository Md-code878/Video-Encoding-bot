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
    # CPU presets are tuned for SPEED on weak machines (Colab free tier).
    # GPU (NVENC) is inherently fast — presets are balanced for quality.

    CODECS = {
        "h264": {
            "gpu": {
                "encoder": "h264_nvenc",
                "params": [
                    "-preset", "p4",
                    "-cq", "24",
                    "-pix_fmt", "yuv420p",
                ],
            },
            "cpu": {
                "encoder": "libx264",
                "params": [
                    "-crf", "23",
                    "-preset", "superfast",   # was "medium" — 10-20x faster
                    "-pix_fmt", "yuv420p",
                    "-threads", "0",           # use all CPU cores
                ],
            },
            "ext": "mkv",
            "label": "H.264",
        },
        "hevc": {
            "gpu": {
                "encoder": "hevc_nvenc",
                "params": [
                    "-preset", "p4",
                    "-cq", "26",
                    "-pix_fmt", "yuv420p",
                ],
            },
            "cpu": {
                "encoder": "libx265",
                "params": [
                    "-crf", "26",
                    "-preset", "ultrafast",    # was "medium" — massive speedup
                    "-pix_fmt", "yuv420p10le",
                    "-x265-params", "pools=*:frame-threads=0",  # max threading
                ],
            },
            "ext": "mkv",
            "label": "H.265 (HEVC)",
        },
        "av1": {
            "gpu": {
                "encoder": "av1_nvenc",
                "params": [
                    "-preset", "p4",
                    "-cq", "30",
                    "-pix_fmt", "yuv420p",
                ],
            },
            "cpu": {
                "encoder": "libsvtav1",
                "params": [
                    "-crf", "32",
                    "-preset", "10",           # was "6" — preset 10 is ~4x faster
                    "-pix_fmt", "yuv420p10le",
                    "-svtav1-params", "fast-decode=1",
                ],
            },
            "ext": "mkv",
            "label": "AV1",
        },
    }

    # Audio: copy if compatible, re-encode only when needed
    # Formats safe to copy into MKV container
    AUDIO_COPY_CODECS = {"aac", "opus", "flac", "vorbis", "mp3", "ac3", "eac3", "dts"}

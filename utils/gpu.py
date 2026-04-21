"""GPU detection and NVENC availability checks."""

import asyncio
import logging
import shutil

logger = logging.getLogger(__name__)

# Cached result
_gpu_info: dict | None = None


async def detect_gpu() -> dict:
    """
    Detect NVIDIA GPU and available NVENC encoders.
    Returns a dict with:
        available: bool
        gpu_name: str
        nvenc_encoders: list[str]  (e.g. ["h264_nvenc", "hevc_nvenc", "av1_nvenc"])
    """
    global _gpu_info
    if _gpu_info is not None:
        return _gpu_info

    info = {"available": False, "gpu_name": "None", "nvenc_encoders": []}

    # Check nvidia-smi
    if not shutil.which("nvidia-smi"):
        logger.info("GPU: nvidia-smi not found — using CPU encoders")
        _gpu_info = info
        return info

    try:
        proc = await asyncio.create_subprocess_exec(
            "nvidia-smi", "--query-gpu=name", "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0 and stdout.strip():
            info["gpu_name"] = stdout.decode().strip().split("\n")[0]
            info["available"] = True
        else:
            logger.info("GPU: nvidia-smi failed — using CPU encoders")
            _gpu_info = info
            return info
    except Exception as e:
        logger.warning(f"GPU: nvidia-smi check failed: {e}")
        _gpu_info = info
        return info

    # Check which NVENC encoders ffmpeg supports
    ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
    try:
        proc = await asyncio.create_subprocess_exec(
            ffmpeg_path, "-hide_banner", "-encoders",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode("utf-8", errors="ignore")

        for enc in ["h264_nvenc", "hevc_nvenc", "av1_nvenc"]:
            if enc in output:
                info["nvenc_encoders"].append(enc)
    except Exception as e:
        logger.warning(f"GPU: ffmpeg encoder check failed: {e}")

    if not info["nvenc_encoders"]:
        logger.info(f"GPU: {info['gpu_name']} found but no NVENC encoders in ffmpeg")
        info["available"] = False
    else:
        logger.info(
            f"GPU: {info['gpu_name']} — NVENC encoders: {info['nvenc_encoders']}"
        )

    _gpu_info = info
    return info


def get_cached_gpu_info() -> dict | None:
    """Return cached GPU info (None if detect_gpu hasn't been called yet)."""
    return _gpu_info


def reset_gpu_cache():
    """Reset the cached GPU info (useful for testing)."""
    global _gpu_info
    _gpu_info = None

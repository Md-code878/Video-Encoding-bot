"""GPU detection and NVENC availability checks."""

import asyncio
import logging
import os
import shutil
import tempfile

logger = logging.getLogger(__name__)

# Cached result
_gpu_info: dict | None = None


async def detect_gpu() -> dict:
    """
    Detect NVIDIA GPU and available NVENC encoders.
    Verifies each encoder actually works by running a tiny test encode.

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
        else:
            logger.info("GPU: nvidia-smi failed — using CPU encoders")
            _gpu_info = info
            return info
    except Exception as e:
        logger.warning(f"GPU: nvidia-smi check failed: {e}")
        _gpu_info = info
        return info

    # Check which NVENC encoders ffmpeg lists
    ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
    listed_encoders = []
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
                listed_encoders.append(enc)
    except Exception as e:
        logger.warning(f"GPU: ffmpeg encoder check failed: {e}")

    if not listed_encoders:
        logger.info(f"GPU: {info['gpu_name']} found but no NVENC encoders in ffmpeg")
        _gpu_info = info
        return info

    # Verify each encoder actually works with a tiny test encode
    for enc in listed_encoders:
        if await _test_nvenc_encoder(ffmpeg_path, enc):
            info["nvenc_encoders"].append(enc)
            logger.info(f"GPU: {enc} — verified working ✓")
        else:
            logger.warning(f"GPU: {enc} — listed but failed test encode ✗")

    if info["nvenc_encoders"]:
        info["available"] = True
        logger.info(
            f"GPU: {info['gpu_name']} — working NVENC encoders: {info['nvenc_encoders']}"
        )
    else:
        logger.info(
            f"GPU: {info['gpu_name']} found but no NVENC encoders passed test encode"
        )

    _gpu_info = info
    return info


async def _test_nvenc_encoder(ffmpeg_path: str, encoder: str) -> bool:
    """
    Test if an NVENC encoder actually works by encoding 1 frame of
    a synthetic test pattern. Returns True if successful.
    """
    tmp_out = None
    try:
        tmp_out = tempfile.mktemp(suffix=".mp4")
        cmd = [
            ffmpeg_path, "-y",
            "-f", "lavfi", "-i", "color=black:s=64x64:d=0.1:r=1",
            "-c:v", encoder,
            "-frames:v", "1",
            tmp_out,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, _ = await proc.communicate()
        return proc.returncode == 0 and os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 0
    except Exception:
        return False
    finally:
        if tmp_out and os.path.exists(tmp_out):
            try:
                os.remove(tmp_out)
            except OSError:
                pass


def get_cached_gpu_info() -> dict | None:
    """Return cached GPU info (None if detect_gpu hasn't been called yet)."""
    return _gpu_info


def reset_gpu_cache():
    """Reset the cached GPU info (useful for testing)."""
    global _gpu_info
    _gpu_info = None

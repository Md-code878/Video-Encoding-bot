import asyncio
import json
import logging
import os
import time
from config import Config
from utils.gpu import detect_gpu

logger = logging.getLogger(__name__)


async def probe_video(filepath: str) -> dict | None:
    """Get full video metadata using ffprobe — including audio codec."""
    cmd = [
        Config.FFPROBE_PATH,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        filepath,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(stdout)
        streams = data.get("streams", [])
        video_stream = next(
            (s for s in streams if s["codec_type"] == "video"), None
        )
        if not video_stream:
            return None

        audio_stream = next(
            (s for s in streams if s["codec_type"] == "audio"), None
        )
        has_subtitles = any(s["codec_type"] == "subtitle" for s in streams)

        return {
            "width": int(video_stream.get("width", 0)),
            "height": int(video_stream.get("height", 0)),
            "duration": float(data.get("format", {}).get("duration", 0)),
            "codec": video_stream.get("codec_name", "unknown"),
            "bitrate": int(data.get("format", {}).get("bit_rate", 0)),
            "size": int(data.get("format", {}).get("size", 0)),
            "fps": _parse_fps(video_stream.get("r_frame_rate", "0/1")),
            "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
            "has_subtitles": has_subtitles,
        }
    except (json.JSONDecodeError, StopIteration, KeyError):
        return None


def _parse_fps(rate_str: str) -> float:
    try:
        num, den = rate_str.split("/")
        return round(int(num) / int(den), 2)
    except (ValueError, ZeroDivisionError):
        return 0.0


async def _pick_encoder(codec: str) -> tuple[str, list[str], bool]:
    """
    Choose GPU or CPU encoder for the given codec.
    Returns (encoder_name, params, is_gpu).
    """
    codec_cfg = Config.CODECS.get(codec)
    if not codec_cfg:
        raise ValueError(f"Unknown codec: {codec}")

    gpu_info = await detect_gpu()
    gpu_variant = codec_cfg.get("gpu", {})
    cpu_variant = codec_cfg["cpu"]

    if (
        gpu_info["available"]
        and gpu_variant
        and gpu_variant["encoder"] in gpu_info["nvenc_encoders"]
    ):
        logger.info(f"Using GPU encoder: {gpu_variant['encoder']}")
        return gpu_variant["encoder"], list(gpu_variant["params"]), True

    logger.info(f"Using CPU encoder: {cpu_variant['encoder']}")
    return cpu_variant["encoder"], list(cpu_variant["params"]), False


def _build_scale_filter(w: int, h: int, fast: bool = False) -> str:
    """
    Build a scale + pad filter.
    fast=True uses bilinear (speed), fast=False uses bicubic (quality).
    """
    flags = "fast_bilinear" if fast else "bicubic"
    return (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags={flags},"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1"
    )


def _build_audio_args(audio_codec: str | None) -> list[str]:
    """
    Smart audio handling: copy if the codec is compatible, re-encode only if needed.
    Copying audio is instant vs re-encoding which wastes CPU time.
    """
    if audio_codec and audio_codec in Config.AUDIO_COPY_CODECS:
        logger.info(f"Audio: copying {audio_codec} (no re-encode needed)")
        return ["-c:a", "copy"]
    else:
        logger.info(f"Audio: re-encoding {audio_codec or 'unknown'} → opus")
        return ["-c:a", "libopus", "-b:a", "128k"]


def _build_ffmpeg_cmd(
    input_path: str,
    output_path: str,
    encoder_name: str,
    encoder_params: list[str],
    resolution: str | None,
    probe_info: dict | None,
    is_cpu_fallback: bool = False,
) -> list[str]:
    """Build the complete ffmpeg command with all optimizations."""
    cmd = [Config.FFMPEG_PATH, "-y", "-threads", "0", "-i", input_path]

    # ── Video filter ─────────────────────────────────────────────
    if resolution:
        res = Config.RESOLUTIONS.get(resolution)
        if res:
            w, h = res
            # Use fast scaling for CPU to save time
            cmd += ["-vf", _build_scale_filter(w, h, fast=is_cpu_fallback)]

    # ── Video codec ──────────────────────────────────────────────
    cmd += ["-c:v", encoder_name]
    cmd += encoder_params

    # ── Audio handling (copy when possible) ──────────────────────
    audio_codec = probe_info.get("audio_codec") if probe_info else None
    cmd += _build_audio_args(audio_codec)

    # ── Stream mapping ───────────────────────────────────────────
    # Map video + audio + subtitles explicitly (skip data/attachment
    # streams that can cause ffmpeg errors and slowdowns)
    cmd += ["-map", "0:v:0"]                     # first video stream
    if audio_codec:
        cmd += ["-map", "0:a?"]                  # all audio streams (if any)
    if probe_info and probe_info.get("has_subtitles"):
        cmd += ["-map", "0:s?"]                  # subtitles (optional)
        cmd += ["-c:s", "copy"]

    # ── Performance flags ────────────────────────────────────────
    cmd += ["-max_muxing_queue_size", "1024"]     # prevent muxing stalls
    cmd += ["-progress", "pipe:1"]
    cmd.append(output_path)

    return cmd


async def encode_video(
    input_path: str,
    output_path: str,
    codec: str,
    resolution: str | None = None,
    progress_callback=None,
) -> tuple[bool, str]:
    """
    Encode a video with the given codec and optional upscale resolution.
    Automatically uses GPU (NVENC) for encoding if available, CPU otherwise.

    Returns (success: bool, message: str).
    """
    try:
        encoder_name, encoder_params, is_gpu = await _pick_encoder(codec)
    except ValueError as e:
        return False, str(e)

    hw_label = "GPU" if is_gpu else "CPU"

    # Probe input for smart audio/stream handling
    probe_info = await probe_video(input_path)
    total_duration = probe_info["duration"] if probe_info else 0

    cmd = _build_ffmpeg_cmd(
        input_path, output_path,
        encoder_name, encoder_params,
        resolution, probe_info,
    )

    logger.info(f"Encoding [{hw_label}]: {' '.join(cmd)}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    start_time = time.time()

    await _read_progress(proc, total_duration, start_time, progress_callback)
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="ignore")[-500:]
        if is_gpu:
            logger.warning(f"GPU encoding failed (code {proc.returncode}): {err[-200:]}")
            logger.info("Retrying with CPU encoder...")
            return await _encode_cpu_fallback(
                input_path, output_path, codec, resolution,
                progress_callback, probe_info,
            )
        return False, f"FFmpeg error (code {proc.returncode}):\n{err}"

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        if is_gpu:
            logger.warning("GPU encoding produced empty output, falling back to CPU")
            return await _encode_cpu_fallback(
                input_path, output_path, codec, resolution,
                progress_callback, probe_info,
            )
        return False, "Encoding produced empty output."

    elapsed = time.time() - start_time
    out_size = os.path.getsize(output_path)
    speed = total_duration / elapsed if elapsed > 0 else 0
    return True, (
        f"Done in {elapsed:.1f}s ({hw_label}) — "
        f"{speed:.1f}x realtime — output {out_size} bytes"
    )


async def _encode_cpu_fallback(
    input_path: str,
    output_path: str,
    codec: str,
    resolution: str | None,
    progress_callback,
    probe_info: dict | None = None,
) -> tuple[bool, str]:
    """CPU-only encoding fallback when GPU fails."""
    codec_cfg = Config.CODECS.get(codec)
    if not codec_cfg:
        return False, f"Unknown codec: {codec}"

    cpu = codec_cfg["cpu"]

    if probe_info is None:
        probe_info = await probe_video(input_path)
    total_duration = probe_info["duration"] if probe_info else 0

    cmd = _build_ffmpeg_cmd(
        input_path, output_path,
        cpu["encoder"], cpu["params"],
        resolution, probe_info,
        is_cpu_fallback=True,
    )

    logger.info(f"Encoding [CPU fallback]: {' '.join(cmd)}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    start_time = time.time()

    await _read_progress(proc, total_duration, start_time, progress_callback)
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="ignore")[-500:]
        return False, f"FFmpeg error (code {proc.returncode}):\n{err}"

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        return False, "Encoding produced empty output."

    elapsed = time.time() - start_time
    out_size = os.path.getsize(output_path)
    speed = total_duration / elapsed if elapsed > 0 else 0
    return True, (
        f"Done in {elapsed:.1f}s (CPU fallback) — "
        f"{speed:.1f}x realtime — output {out_size} bytes"
    )


async def _read_progress(proc, total_duration, start_time, progress_callback):
    """Read ffmpeg progress output and call the callback."""
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        line = line.decode("utf-8", errors="ignore").strip()
        if line.startswith("out_time_us="):
            try:
                current_us = int(line.split("=")[1])
            except ValueError:
                continue
            if progress_callback and total_duration > 0:
                pct = min((current_us / 1_000_000) / total_duration * 100, 99.9)
                elapsed = time.time() - start_time
                await progress_callback(pct, elapsed)

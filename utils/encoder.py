import asyncio
import json
import logging
import os
import time
from config import Config
from utils.gpu import detect_gpu

logger = logging.getLogger(__name__)


async def probe_video(filepath: str) -> dict | None:
    """Get video metadata using ffprobe."""
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
        video_stream = next(
            (s for s in data.get("streams", []) if s["codec_type"] == "video"), None
        )
        if not video_stream:
            return None
        return {
            "width": int(video_stream.get("width", 0)),
            "height": int(video_stream.get("height", 0)),
            "duration": float(data.get("format", {}).get("duration", 0)),
            "codec": video_stream.get("codec_name", "unknown"),
            "bitrate": int(data.get("format", {}).get("bit_rate", 0)),
            "size": int(data.get("format", {}).get("size", 0)),
            "fps": _parse_fps(video_stream.get("r_frame_rate", "0/1")),
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

    # Try GPU if available and the specific NVENC encoder is supported
    if (
        gpu_info["available"]
        and gpu_variant
        and gpu_variant["encoder"] in gpu_info["nvenc_encoders"]
    ):
        logger.info(f"Using GPU encoder: {gpu_variant['encoder']}")
        return gpu_variant["encoder"], gpu_variant["params"], True

    logger.info(f"Using CPU encoder: {cpu_variant['encoder']}")
    return cpu_variant["encoder"], cpu_variant["params"], False


async def encode_video(
    input_path: str,
    output_path: str,
    codec: str,
    resolution: str | None = None,
    progress_callback=None,
) -> tuple[bool, str]:
    """
    Encode a video with the given codec and optional upscale resolution.
    Automatically uses GPU (NVENC) if available, CPU otherwise.

    Returns (success: bool, message: str).
    """
    try:
        encoder_name, encoder_params, is_gpu = await _pick_encoder(codec)
    except ValueError as e:
        return False, str(e)

    hw_label = "GPU" if is_gpu else "CPU"

    # Build ffmpeg command
    cmd = [Config.FFMPEG_PATH, "-y"]

    # For NVENC, use hwaccel for decoding too (optional but faster)
    if is_gpu:
        cmd += ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]

    cmd += ["-i", input_path]

    # Video filters (upscaling)
    vf_filters = []
    if resolution:
        res = Config.RESOLUTIONS.get(resolution)
        if not res:
            return False, f"Unknown resolution: {resolution}"
        w, h = res

        if is_gpu:
            # Use NVIDIA's hardware scaler on GPU
            # Need to upload to GPU if not already there, scale, then download
            vf_filters.append(
                f"scale_cuda={w}:{h}:force_original_aspect_ratio=decrease"
            )
            # Pad on GPU isn't available in scale_cuda, so we need a mixed approach
            # Use hwdownload + pad + hwupload, or just use scale_cuda with specific dims
            # Simpler: force exact dimensions with scale_cuda
            vf_filters = [
                f"scale_cuda={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2"
            ]
        else:
            vf_filters.append(
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
                f"setsar=1"
            )

    if is_gpu and not vf_filters:
        # No scaling needed but we're using cuda hwaccel — no filter needed,
        # NVENC can encode from cuda frames directly
        pass
    elif is_gpu and vf_filters:
        cmd += ["-vf", ",".join(vf_filters)]
    elif vf_filters:
        cmd += ["-vf", ",".join(vf_filters)]

    # Codec settings
    cmd += ["-c:v", encoder_name]
    cmd += encoder_params

    # Audio: copy or re-encode to opus
    cmd += ["-c:a", "libopus", "-b:a", "128k"]

    # Subtitle copy (if container supports)
    cmd += ["-c:s", "copy"]

    # Map all streams
    cmd += ["-map", "0"]

    # Progress tracking via pipe
    cmd += ["-progress", "pipe:1"]

    cmd.append(output_path)

    # Get input duration for progress
    probe = await probe_video(input_path)
    total_duration = probe["duration"] if probe else 0

    logger.info(f"Encoding [{hw_label}]: {' '.join(cmd)}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    start_time = time.time()
    current_time_us = 0

    # Read progress from stdout
    async def read_progress():
        nonlocal current_time_us
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            line = line.decode("utf-8", errors="ignore").strip()
            if line.startswith("out_time_us="):
                try:
                    current_time_us = int(line.split("=")[1])
                except ValueError:
                    pass
                if progress_callback and total_duration > 0:
                    pct = min(
                        (current_time_us / 1_000_000) / total_duration * 100, 99.9
                    )
                    elapsed = time.time() - start_time
                    await progress_callback(pct, elapsed)

    await read_progress()
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="ignore")[-500:]

        # If GPU encoding failed, retry with CPU fallback
        if is_gpu:
            logger.warning(
                f"GPU encoding failed (code {proc.returncode}), falling back to CPU"
            )
            return await _encode_cpu_fallback(
                input_path, output_path, codec, resolution, progress_callback
            )

        return False, f"FFmpeg error (code {proc.returncode}):\n{err}"

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        if is_gpu:
            logger.warning("GPU encoding produced empty output, falling back to CPU")
            return await _encode_cpu_fallback(
                input_path, output_path, codec, resolution, progress_callback
            )
        return False, "Encoding produced empty output."

    elapsed = time.time() - start_time
    out_size = os.path.getsize(output_path)
    return True, f"Done in {elapsed:.1f}s ({hw_label}) — output {out_size} bytes"


async def _encode_cpu_fallback(
    input_path: str,
    output_path: str,
    codec: str,
    resolution: str | None,
    progress_callback,
) -> tuple[bool, str]:
    """CPU-only encoding fallback when GPU fails."""
    codec_cfg = Config.CODECS.get(codec)
    if not codec_cfg:
        return False, f"Unknown codec: {codec}"

    cpu = codec_cfg["cpu"]

    cmd = [Config.FFMPEG_PATH, "-y", "-i", input_path]

    # Video filters (CPU path)
    if resolution:
        res = Config.RESOLUTIONS.get(resolution)
        if res:
            w, h = res
            cmd += [
                "-vf",
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
                f"setsar=1",
            ]

    cmd += ["-c:v", cpu["encoder"]]
    cmd += cpu["params"]
    cmd += ["-c:a", "libopus", "-b:a", "128k"]
    cmd += ["-c:s", "copy"]
    cmd += ["-map", "0"]
    cmd += ["-progress", "pipe:1"]
    cmd.append(output_path)

    probe = await probe_video(input_path)
    total_duration = probe["duration"] if probe else 0

    logger.info(f"Encoding [CPU fallback]: {' '.join(cmd)}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    start_time = time.time()

    async def read_progress():
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            line = line.decode("utf-8", errors="ignore").strip()
            if line.startswith("out_time_us="):
                try:
                    t = int(line.split("=")[1])
                except ValueError:
                    continue
                if progress_callback and total_duration > 0:
                    pct = min((t / 1_000_000) / total_duration * 100, 99.9)
                    elapsed = time.time() - start_time
                    await progress_callback(pct, elapsed)

    await read_progress()
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="ignore")[-500:]
        return False, f"FFmpeg error (code {proc.returncode}):\n{err}"

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        return False, "Encoding produced empty output."

    elapsed = time.time() - start_time
    out_size = os.path.getsize(output_path)
    return True, f"Done in {elapsed:.1f}s (CPU fallback) — output {out_size} bytes"

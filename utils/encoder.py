import asyncio
import json
import os
import time
from config import Config


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


async def encode_video(
    input_path: str,
    output_path: str,
    codec: str,
    resolution: str | None = None,
    progress_callback=None,
) -> tuple[bool, str]:
    """
    Encode a video with the given codec and optional upscale resolution.

    Returns (success: bool, message: str).
    """
    codec_cfg = Config.CODECS.get(codec)
    if not codec_cfg:
        return False, f"Unknown codec: {codec}"

    # Build ffmpeg command
    cmd = [Config.FFMPEG_PATH, "-y", "-i", input_path]

    # Video filters (upscaling)
    vf_filters = []
    if resolution:
        res = Config.RESOLUTIONS.get(resolution)
        if not res:
            return False, f"Unknown resolution: {resolution}"
        w, h = res
        # Lanczos upscale, force even dimensions
        vf_filters.append(
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1"
        )
        vf_filters[-1] = vf_filters[-1]  # Lanczos is default in ffmpeg scale

    if vf_filters:
        cmd += ["-vf", ",".join(vf_filters)]

    # Codec settings
    cmd += ["-c:v", codec_cfg["encoder"]]
    cmd += codec_cfg["params"]

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
        return False, f"FFmpeg error (code {proc.returncode}):\n{err}"

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        return False, "Encoding produced empty output."

    elapsed = time.time() - start_time
    out_size = os.path.getsize(output_path)
    return True, f"Done in {elapsed:.1f}s — output {out_size} bytes"

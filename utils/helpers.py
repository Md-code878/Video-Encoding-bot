import math
import time
from pyrogram import Client
from pyrogram.types import Message


def humanbytes(size: int | float) -> str:
    """Convert bytes to human-readable string."""
    if not size:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    power = int(math.log(size, 1024))
    power = min(power, len(units) - 1)
    return f"{size / (1024 ** power):.2f} {units[power]}"


def time_formatter(seconds: float) -> str:
    """Convert seconds to human-readable time string."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    return f"{minutes}m {seconds}s"


async def progress_callback(current: int, total: int, message: Message, start_time: float, action: str = "Processing"):
    """Generic progress callback for uploads/downloads."""
    now = time.time()
    elapsed = now - start_time

    # Throttle updates to every 5 seconds
    if not hasattr(progress_callback, "_last_update"):
        progress_callback._last_update = {}
    msg_key = f"{message.chat.id}_{message.id}"
    last = progress_callback._last_update.get(msg_key, 0)
    if now - last < 5:
        return
    progress_callback._last_update[msg_key] = now

    if total == 0:
        return

    pct = current / total * 100
    speed = current / elapsed if elapsed > 0 else 0
    eta = (total - current) / speed if speed > 0 else 0

    bar_length = 12
    filled = int(bar_length * current / total)
    bar = "█" * filled + "░" * (bar_length - filled)

    text = (
        f"**{action}...**\n\n"
        f"`[{bar}]` {pct:.1f}%\n"
        f"**Done:** {humanbytes(current)} / {humanbytes(total)}\n"
        f"**Speed:** {humanbytes(speed)}/s\n"
        f"**ETA:** {time_formatter(eta)}"
    )

    try:
        await message.edit_text(text)
    except Exception:
        pass

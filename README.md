# 🎬 Telegram Video Encoder & Upscaler Bot

A powerful open-source Telegram bot that encodes videos to **H.264**, **H.265 (HEVC)**, or **AV1** and upscales them to **1080p, 2K, 4K, or 8K** using FFmpeg — with **automatic NVIDIA GPU acceleration** on Google Colab.

## ✨ Features

- **Video Encoding** — H.264, H.265/HEVC, and AV1
- **🚀 GPU Acceleration** — Auto-detects NVIDIA GPU and uses NVENC hardware encoding (5-20x faster)
- **Auto Fallback** — Gracefully falls back to CPU encoding if GPU unavailable or fails
- **Video Upscaling** — 1080p (1920×1080), 2K (2560×1440), 4K (3840×2160), 8K (7680×4320)
- **Progress Tracking** — Real-time progress bars for download, encode, and upload
- **User Settings** — Save preferred codec and resolution defaults
- **Admin Panel** — Ban/unban users, broadcast messages, GPU & system status, view logs
- **MongoDB Storage** — User data, task history, and settings persistence
- **Log Channel** — All encode activities logged to a Telegram channel
- **Queue System** — Configurable concurrent worker limit
- **Media Info** — Probe video metadata before encoding
- **Docker Support** — Ready-to-deploy Dockerfile included

## 🚀 GPU Acceleration

The bot automatically detects NVIDIA GPUs and uses hardware NVENC encoders:

| Codec | GPU Encoder | CPU Fallback | Google Colab |
|-------|-------------|--------------|--------------|
| H.264 | `h264_nvenc` | `libx264` | ✅ All GPUs |
| HEVC | `hevc_nvenc` | `libx265` | ✅ All GPUs |
| AV1 | `av1_nvenc` | `libsvtav1` | ✅ L4/A100 only* |

*T4 GPUs don't support AV1 NVENC — the bot auto-falls back to CPU for AV1 on T4.

### Google Colab Setup

```python
# Install dependencies in a Colab cell
!pip install pyrogram tgcrypto motor pymongo python-dotenv psutil aiofiles

# Upload your config.env or set variables
import os
os.environ['BOT_TOKEN'] = 'your-bot-token'
os.environ['API_ID'] = 'your-api-id'
os.environ['API_HASH'] = 'your-api-hash'
os.environ['ADMIN_IDS'] = 'your-user-id'
os.environ['MONGO_URI'] = 'your-mongo-uri'

# Check GPU
!nvidia-smi

# Run the bot
!python bot.py
```

The bot will log which encoders are available at startup:
```
🚀 GPU detected: Tesla T4
🚀 NVENC encoders: ['h264_nvenc', 'hevc_nvenc']
```

## 📋 Commands

### User Commands
| Command | Description |
|---------|-------------|
| `/start` | Start the bot |
| `/help` | Show help message |
| `/encode` | Encode a video (reply to video) |
| `/upscale` | Upscale a video (reply to video) |
| `/settings` | View/change encoding preferences |
| `/stats` | Bot statistics |
| `/mediainfo` | Get video metadata (reply to video) |
| `/cancel` | Cancel current encode |

### Admin Commands
| Command | Description |
|---------|-------------|
| `/ban <user_id>` | Ban a user |
| `/unban <user_id>` | Unban a user |
| `/broadcast <msg>` | Broadcast to all users |
| `/status` | System + GPU resource status |
| `/logs` | View recent bot logs |

## 🚀 Setup

### Prerequisites
- Python 3.10+
- FFmpeg (with codec support; NVENC requires NVIDIA drivers)
- MongoDB instance
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Telegram API ID & Hash (from [my.telegram.org](https://my.telegram.org))

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Md-code878/Video-Encoding-bot
   cd Video-Encoding-bot
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the bot:**
   ```bash
   cp config.env.example config.env
   # Edit config.env with your values
   nano config.env
   ```

4. **Run the bot:**
   ```bash
   python bot.py
   ```

### Docker

```bash
# Build
docker build -t video-encoder-bot .

# Run
docker run -d \
  --name video-encoder-bot \
  -v ./config.env:/app/config.env \
  -v ./downloads:/app/downloads \
  video-encoder-bot
```

For GPU support in Docker, use the NVIDIA runtime:
```bash
docker run -d --gpus all \
  --name video-encoder-bot \
  -v ./config.env:/app/config.env \
  -v ./downloads:/app/downloads \
  video-encoder-bot
```

## ⚙️ Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `BOT_TOKEN` | Telegram bot token | — |
| `API_ID` | Telegram API ID | — |
| `API_HASH` | Telegram API Hash | — |
| `ADMIN_IDS` | Comma-separated admin user IDs | — |
| `MONGO_URI` | MongoDB connection string | — |
| `DB_NAME` | MongoDB database name | `videoencoderbot` |
| `LOG_CHANNEL` | Telegram channel ID for logs | — |
| `MAX_FILE_SIZE` | Max file size in bytes | `2147483648` (2GB) |
| `MAX_WORKERS` | Concurrent encode workers | `2` |
| `TEMP_DIR` | Temporary download directory | `./downloads` |

## 📐 Encoding Presets

### Codecs (GPU / CPU)
- **H.264:** `h264_nvenc` (GPU) / `libx264` (CPU) — fastest, most compatible
- **HEVC:** `hevc_nvenc` (GPU) / `libx265` (CPU) — great quality/size ratio
- **AV1:** `av1_nvenc` (GPU, Ada+) / `libsvtav1` (CPU) — best compression, newer

### Resolutions
- **1080p:** 1920 × 1080
- **2K:** 2560 × 1440
- **4K:** 3840 × 2160
- **8K:** 7680 × 4320

Audio is re-encoded to Opus at 128kbps. Subtitles are copied when supported.
GPU scaling uses `scale_cuda` for hardware-accelerated resize.

## 🏗️ Project Structure

```
telegram-video-bot/
├── bot.py                  # Main entry point (GPU detection at startup)
├── config.py               # Configuration + codec definitions (GPU/CPU)
├── config.env.example      # Example configuration
├── commands.py             # Command handlers
├── database.py             # MongoDB operations
├── requirements.txt        # Python dependencies
├── Dockerfile              # Docker support
├── LICENSE                 # MIT License
├── plugins/
│   ├── callbacks.py        # Inline button callbacks
│   └── video_handler.py    # Video processing pipeline
└── utils/
    ├── encoder.py          # FFmpeg encoding (GPU + CPU fallback)
    ├── gpu.py              # NVIDIA GPU detection & NVENC checks
    └── helpers.py          # Utility functions
```

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open a Pull Request

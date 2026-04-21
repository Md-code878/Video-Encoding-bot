# 🎬 Telegram Video Encoder & Upscaler Bot

A powerful open-source Telegram bot that encodes videos to **AV1** or **H.265 (HEVC)** and upscales them to **1080p, 2K, 4K, or 8K** using FFmpeg.

## ✨ Features

- **Video Encoding** — AV1 (libsvtav1) and H.265/HEVC (libx265)
- **Video Upscaling** — 1080p (1920×1080), 2K (2560×1440), 4K (3840×2160), 8K (7680×4320)
- **Progress Tracking** — Real-time progress bars for download, encode, and upload
- **User Settings** — Save preferred codec and resolution defaults
- **Admin Panel** — Ban/unban users, broadcast messages, system status, view logs
- **MongoDB Storage** — User data, task history, and settings persistence
- **Log Channel** — All encode activities logged to a Telegram channel
- **Queue System** — Configurable concurrent worker limit
- **Media Info** — Probe video metadata before encoding
- **Docker Support** — Ready-to-deploy Dockerfile included

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
| `/status` | System resource status |
| `/logs` | View recent bot logs |

## 🚀 Setup

### Prerequisites
- Python 3.10+
- FFmpeg (with libsvtav1 and libx265 support)
- MongoDB instance
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Telegram API ID & Hash (from [my.telegram.org](https://my.telegram.org))

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Md-code878/Video-Encoding-bot
   cd telegram-video-bot
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

### Codecs
- **HEVC (H.265):** `libx265`, CRF 24, medium preset, 10-bit
- **AV1:** `libsvtav1`, CRF 30, preset 6, 10-bit

### Resolutions
- **1080p:** 1920 × 1080
- **2K:** 2560 × 1440
- **4K:** 3840 × 2160
- **8K:** 7680 × 4320

Audio is re-encoded to Opus at 128kbps. Subtitles are copied when supported.

## 🏗️ Project Structure

```
telegram-video-bot/
├── bot.py                  # Main entry point
├── config.py               # Configuration loader
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
    ├── encoder.py          # FFmpeg encoding logic
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

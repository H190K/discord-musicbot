#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
#   Linux server setup for the music bot
#
#   ./setup.sh            install system packages + Python deps + tools
#   ./setup.sh systemd    also install a systemd service (needs sudo)
#
#   Desktop users don't need this — just run ./start.sh
# ═══════════════════════════════════════════════════════════════════
set -e
cd "$(dirname "$0")"
BOT_DIR="$(pwd)"
BOT_USER="${SUDO_USER:-$(id -un)}"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    SUDO="sudo"
fi

echo "🎵 Music bot setup in $BOT_DIR"

# System packages (Python + venv + libsodium for voice; FFmpeg is optional,
# update_deps.py downloads a static build into bin/ anyway)
if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update -qq
    $SUDO apt-get install -y -qq python3 python3-venv python3-pip ffmpeg libsodium-dev
elif command -v dnf >/dev/null 2>&1; then
    $SUDO dnf install -y python3 python3-pip ffmpeg-free libsodium
elif command -v pacman >/dev/null 2>&1; then
    $SUDO pacman -S --noconfirm --needed python python-pip ffmpeg libsodium
else
    echo "⚠️  Unknown package manager — install Python 3.10+ yourself."
fi

# Python environment + packages
if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt -q

# yt-dlp + Deno + FFmpeg into bin/
.venv/bin/python update_deps.py

if [ ! -f config.txt ]; then
    cp config.example.txt config.txt
    echo "📝 Created config.txt — put your bot token in it before starting."
fi

if [ "$1" = "systemd" ]; then
    SERVICE_FILE=/etc/systemd/system/music-bot.service
    $SUDO tee "$SERVICE_FILE" >/dev/null <<UNIT
[Unit]
Description=Discord music bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$BOT_USER
WorkingDirectory=$BOT_DIR
ExecStart=$BOT_DIR/.venv/bin/python $BOT_DIR/launcher.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable music-bot
    echo "✅ Service installed. Start it with: sudo systemctl start music-bot"
    echo "   Logs: journalctl -u music-bot -f"
else
    echo "✅ Setup done. Start the bot with: ./start.sh"
fi

#!/bin/bash
# Run the Tijdvorm stream receiver
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "No venv found. Run setup.sh first."
    exit 1
fi

# Don't force a video driver — receiver.py tries kmsdrm, fbdev, x11 in order
unset SDL_VIDEODRIVER 2>/dev/null

echo "Starting Tijdvorm Stream Receiver..."
echo "Stream URL: ${STREAM_URL:-http://mini.netlob:8000/stream}"

exec ./venv/bin/python receiver.py

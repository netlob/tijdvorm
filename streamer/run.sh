#!/bin/bash
# Run the Tijdvorm stream receiver
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "No venv found. Run setup.sh first."
    exit 1
fi

# Use KMS/DRM backend for SDL2 (no X server needed)
# Falls back to fbdev or X11 if KMS isn't available
export SDL_VIDEODRIVER="${SDL_VIDEODRIVER:-kmsdrm}"

echo "Starting Tijdvorm Stream Receiver..."
echo "Stream URL: ${STREAM_URL:-http://mini.netlob:8000/stream}"
echo "SDL driver: $SDL_VIDEODRIVER"

exec ./venv/bin/python receiver.py

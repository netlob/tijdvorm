#!/bin/bash
# Run the Tijdvorm stream receiver
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "No venv found. Run setup.sh first."
    exit 1
fi

echo "Starting Tijdvorm Stream Receiver..."
echo "Stream URL: ${STREAM_URL:-http://mini.netlob:8000/stream}"

# If X is already running, use it directly
if [ -n "$DISPLAY" ] || pgrep -x Xorg > /dev/null 2>&1; then
    export DISPLAY="${DISPLAY:-:0}"
    export SDL_VIDEODRIVER=x11
    exec ./venv/bin/python receiver.py
fi

# No X running — start minimal X server via xinit (no desktop/WM needed)
if command -v xinit > /dev/null 2>&1; then
    echo "No display server found, starting minimal X via xinit..."
    exec xinit "$(pwd)/start_receiver.sh" -- :0 -nocursor
fi

# Last resort: try without X (kmsdrm/fbdev)
echo "No xinit available, trying direct rendering..."
unset SDL_VIDEODRIVER 2>/dev/null
exec ./venv/bin/python receiver.py

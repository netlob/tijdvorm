#!/bin/bash
# This script is called by xinit
# $1 is the URL passed from main.py

# Disable screen saver / energy saving
xset -dpms
xset s off
xset s noblank

# Rotate the display for Portrait TV
# We send 1920x1080 signal, but render 1080x1920 desktop
xrandr --output HDMI-1 --rotate right

# Start window manager in background
openbox &

# Start Chromium
# --window-size=1080,1920 : forceful size (though kiosk usually handles it)
# --kiosk : Fullscreen mode
# --incognito : No cache/history
chromium-browser \
    --no-first-run \
    --kiosk \
    --incognito \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --check-for-update-interval=31536000 \
    --window-position=0,0 \
    --window-size=1080,1920 \
    "$1"


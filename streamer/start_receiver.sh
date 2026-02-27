#!/bin/bash
# Called by xinit — runs inside X server session
# Disables screensaver/DPMS so display stays on

xset -dpms
xset s off
xset s noblank

# Wait for display to be ready
sleep 1

# Rotate display to portrait (right = 90° CW)
# The Samsung Frame TV auto-rotates when mounted vertically,
# so we DON'T use software rotation in the receiver (ROTATION=0).
# Instead, xrandr rotates the X display so the Pi outputs portrait natively.
xrandr --output HDMI-1 --rotate right 2>/dev/null || \
xrandr --output HDMI-2 --rotate right 2>/dev/null || \
echo "xrandr rotate failed — check output name with 'xrandr --query'"

cd "$(dirname "$0")"
export SDL_VIDEODRIVER=x11
export ROTATION=0
exec ./venv/bin/python receiver.py

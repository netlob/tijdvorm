#!/bin/bash
# Called by xinit — runs inside X server session
# Disables screensaver/DPMS so display stays on

xset -dpms
xset s off
xset s noblank

cd "$(dirname "$0")"
export SDL_VIDEODRIVER=x11

# The backend generates 1080x1920 (portrait) images.
# The Pi outputs standard 1920x1080 HDMI (landscape).
# ROTATION=270 rotates the portrait image 90° CW to fill the
# 1920x1080 output. On the portrait-mounted Samsung Frame TV
# (right side up), the viewer sees correct portrait orientation.
export ROTATION=270
exec ./venv/bin/python receiver.py

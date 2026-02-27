#!/bin/bash
# Called by xinit — runs inside X server session
# Disables screensaver/DPMS so display stays on

xset -dpms
xset s off
xset s noblank

cd "$(dirname "$0")"
export SDL_VIDEODRIVER=x11
exec ./venv/bin/python receiver.py

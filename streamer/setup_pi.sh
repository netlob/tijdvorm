#!/bin/bash
# Install dependencies for Chromium Kiosk on Raspbian Lite

echo "Installing X11, Window Manager, and Chromium..."
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    xserver-xorg \
    x11-xserver-utils \
    xinit \
    openbox \
    chromium-browser \
    python3-venv \
    python3-pip

# Basic setup for openbox (prevents black screen / ensures full screen)
mkdir -p ~/.config/openbox
cat > ~/.config/openbox/rc.xml <<EOL
<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/rc" xmlns:xi="http://www.w3.org/2001/XInclude">
<applications>
  <application class="*">
    <decor>no</decor>
    <maximized>yes</maximized>
  </application>
</applications>
</openbox_config>
EOL

echo "Dependencies installed. You can now run the streamer."


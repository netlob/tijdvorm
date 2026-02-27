#!/bin/bash
# Setup script for Tijdvorm Stream Receiver on Raspberry Pi
# Run once after cloning the repo on the Pi

set -e

echo "=== Tijdvorm Stream Receiver Setup ==="

# Install system dependencies for SDL2 (Pygame) and Python
echo "Installing system packages..."
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    python3-venv \
    python3-pip \
    python3-dev \
    libsdl2-2.0-0 \
    libsdl2-image-2.0-0 \
    libsdl2-mixer-2.0-0 \
    libsdl2-ttf-2.0-0 \
    libjpeg-dev \
    libfreetype6-dev

# Add user to video group for KMS/DRM access (framebuffer without X)
echo "Adding user to video group..."
sudo usermod -aG video "$USER"

# Create Python venv and install deps
echo "Setting up Python environment..."
cd "$(dirname "$0")"

if [ -d "venv" ]; then
    echo "Removing old venv..."
    rm -rf venv
fi

python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# Install systemd service
echo "Installing systemd service..."
sudo cp tijdvorm-receiver.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tijdvorm-receiver

echo ""
echo "=== Setup complete ==="
echo "Configure the stream URL in /etc/default/tijdvorm-receiver or via environment."
echo "Start with: sudo systemctl start tijdvorm-receiver"
echo "Logs: journalctl -u tijdvorm-receiver -f"
echo ""
echo "NOTE: If using KMS/DRM (no X server), you may need to reboot for"
echo "video group membership to take effect."

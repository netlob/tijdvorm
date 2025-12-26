#!/bin/bash
# HDMI Diagnostics for Raspberry Pi
echo "=== HDMI Diagnostics ==="

# 1. Check current HDMI status
echo -e "\n1. Current HDMI Power Status:"
vcgencmd display_power 0  # Check HDMI 0 (main HDMI port)

echo -e "\n2. Display Information:"
vcgencmd get_lcd_info  # Should show resolution if display is connected
vcgencmd dispmanx_list  # List displays

# Try tvservice if available (older Raspberry Pi OS)
if command -v tvservice >/dev/null 2>&1; then
    echo "TV Service Status:"
    tvservice -s
else
    echo "tvservice not available (newer Raspberry Pi OS)"
fi

# Alternative display info
echo "Display Power Status:"
vcgencmd display_power 0

echo "EDID Information:"
vcgencmd edidparser /sys/class/drm/card*/edid 2>/dev/null | head -20 || echo "EDID not readable"

echo -e "\n3. HDMI Configuration:"
# Check config.txt for HDMI settings
grep -E "^(hdmi_|display_)" /boot/config.txt 2>/dev/null || echo "No HDMI config found in /boot/config.txt"

echo -e "\n4. HyperHDR Status:"
# Check if HyperHDR is running and its config
systemctl status hyperhdr 2>/dev/null | head -10 || echo "HyperHDR not running or not installed"

echo -e "\n5. X Server Status:"
# Check if X is running
ps aux | grep -E "(X|xinit)" | grep -v grep || echo "No X server running"

echo -e "\n6. Network Interfaces:"
# Check network (to confirm connectivity)
ip addr show eth0 2>/dev/null | grep inet || echo "No ethernet IP found"

echo -e "\n7. Current Processes:"
# Check what processes might be using HDMI
ps aux | grep -E "(hyperhdr|kodi|chromium|openbox)" | grep -v grep || echo "No HDMI-related processes found"

echo -e "\n=== Quick Fixes ==="
echo "To re-enable HDMI: sudo vcgencmd display_power 0 1"
echo "To restart HyperHDR: sudo systemctl restart hyperhdr"
echo "To check HyperHDR config: nano ~/.hyperhdr/db/hyperhdr.db"

import os

# Backend MJPEG stream URL
STREAM_URL = os.environ.get("STREAM_URL", "http://m4.netlob:8000/stream")

# Display rotation in degrees (0, 90, 180, 270)
# 180 = TV mounted upside-down in portrait
ROTATION = int(os.environ.get("ROTATION", "270"))

# Reconnect settings
RECONNECT_DELAY = float(os.environ.get("RECONNECT_DELAY", "2.0"))
RECONNECT_MAX_DELAY = float(os.environ.get("RECONNECT_MAX_DELAY", "30.0"))

# Background color shown before first frame / on error
BG_COLOR = (0, 0, 0)

# JPEG read buffer size (64KB chunks)
READ_CHUNK_SIZE = 65536

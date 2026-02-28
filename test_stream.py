
"""
Temporary test MJPEG stream server.
Run this on your Mac to test the Pi receiver before the real backend is ready.

Usage: python test_stream.py
Then point the Pi receiver at http://<your-mac-ip>:8000/stream
"""

import asyncio
import io
import time
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from PIL import Image, ImageDraw, ImageFont

app = FastAPI(title="Test MJPEG Stream")

# Frame size matching the TV portrait resolution
WIDTH = 1080
HEIGHT = 1920

# Colors to cycle through
COLORS = [
    # (20, 20, 30),      # Dark blue-black
    # (40, 15, 15),      # Dark red
    # (15, 35, 15),      # Dark green
    # (30, 20, 40),      # Dark purple
    # (35, 30, 10),      # Dark amber
    (0, 0, 0),      # Dark amber
]


def generate_test_frame(frame_num: int) -> bytes:
    """Generate a test frame with timestamp and color cycling."""
    color = COLORS[frame_num % len(COLORS)]
    img = Image.new("RGB", (WIDTH, HEIGHT), color)
    draw = ImageDraw.Draw(img)

    now = datetime.now()
    timestamp = now.strftime("%H:%M:%S")
    date_str = now.strftime("%Y-%m-%d")

    # Use a basic font (will be available on most systems)
    try:
        font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 120)
        font_medium = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 60)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
    except (OSError, IOError):
        font_large = ImageFont.load_default()
        font_medium = font_large
        font_small = font_large

    # Draw centered timestamp
    text_color = (255, 255, 255)
    dim_color = (120, 120, 120)

    # Time - center of screen
    bbox = draw.textbbox((0, 0), timestamp, font=font_large)
    tw = bbox[2] - bbox[0]
    draw.text(((WIDTH - tw) // 2, HEIGHT // 2 - 80), timestamp, fill=text_color, font=font_large)

    # Date - below time
    bbox = draw.textbbox((0, 0), date_str, font=font_medium)
    tw = bbox[2] - bbox[0]
    draw.text(((WIDTH - tw) // 2, HEIGHT // 2 + 80), date_str, fill=dim_color, font=font_medium)

    # Frame counter and stream info
    info = f"Frame #{frame_num}"
    bbox = draw.textbbox((0, 0), info, font=font_small)
    tw = bbox[2] - bbox[0]
    draw.text(((WIDTH - tw) // 2, HEIGHT - 200), info, fill=dim_color, font=font_small)

    label = "MJPEG Test Stream"
    bbox = draw.textbbox((0, 0), label, font=font_small)
    tw = bbox[2] - bbox[0]
    draw.text(((WIDTH - tw) // 2, 100), label, fill=dim_color, font=font_small)

    # Encode as JPEG
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


async def mjpeg_stream():
    """Generate MJPEG multipart stream with variable frame rate."""
    frame_num = 0
    boundary = b"frame"

    while True:
        jpeg_bytes = generate_test_frame(frame_num)

        yield (
            b"--" + boundary + b"\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(jpeg_bytes)).encode() + b"\r\n"
            b"\r\n" + jpeg_bytes + b"\r\n"
        )

        frame_num += 1

        await asyncio.sleep(0.2)
        # Variable frame rate demo:
        # 3 frames at 1 FPS (1s interval), then 5 seconds of 5 FPS (0.2s interval)
        # cycle = frame_num % 8
        # if cycle < 3:
        #     # 1 FPS for 3 frames (1 second between frames)
        #     await asyncio.sleep(1.0)
        # else:
        #     # 5 FPS for 5 seconds (0.2 second between frames, 5 frames)
        #     await asyncio.sleep(0.2)


@app.get("/stream")
async def stream():
    return StreamingResponse(
        mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/health")
async def health():
    return {"status": "ok", "mode": "test"}


if __name__ == "__main__":
    import uvicorn

    print("Starting test MJPEG stream on http://0.0.0.0:8000/stream")
    print("Open in browser or point the Pi receiver at this URL")
    uvicorn.run(app, host="0.0.0.0", port=8000)
#!/usr/bin/env python3
"""
Test MJPEG server that proxies the Reolink doorbell RTSP feed
with a styled overlay matching the tijdvorm art display.

Runs ffmpeg on the host (outside Docker) to grab the RTSP stream,
composites each frame into a styled doorbell UI, and serves as MJPEG.

Usage:
    python test_doorbell_stream.py
    python test_doorbell_stream.py --url rtsp://admin:pass@10.0.1.45:554/h264Preview_01_main
    python test_doorbell_stream.py --port 8000
    python test_doorbell_stream.py --raw   # skip overlay, pass through raw frames
"""

import argparse
import asyncio
import concurrent.futures
import io
import logging
import os
import time

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from PIL import Image, ImageDraw, ImageFont

# Try loading .env for defaults
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("doorbell_proxy")

DEFAULT_URL = os.environ.get(
    "NVR_RTSP_URL",
    "rtsp://admin:peepeeDoorbell%24123poopoo@10.0.1.45:554/h264Preview_01_main",
)

# ── Layout constants (matching timeform art overlay) ──────────────────────
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
TEXT_PADDING = 50  # Same side padding as timeform art text
CONTENT_WIDTH = OUTPUT_WIDTH - 2 * TEXT_PADDING  # 930
CORNER_RADIUS = 35

# Colours
BG_COLOR = (250, 250, 252)
HEADER_COLOR = (40, 40, 50)
NAME_COLOR = (40, 40, 50)
SUBTITLE_COLOR = (140, 140, 155)
AVATAR_BG = (215, 215, 225)
AVATAR_FG = (175, 175, 185)
BELL_COLOR = (210, 160, 30)  # Gold
CAMERA_BG = (25, 25, 30)  # Dark placeholder

# Font sizes
HEADER_FONT_SIZE = 75
NAME_FONT_SIZE = 55
SUBTITLE_FONT_SIZE = 45

# Person section
AVATAR_SIZE = 180

# Font paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH_SFNS = os.path.join(SCRIPT_DIR, "assets", "fonts", "SFNS.ttf")
FONT_PATH_FALLBACK = "/System/Library/Fonts/Helvetica.ttc"


# Target FPS for the composed output stream
TARGET_FPS = 5

# ── Shared state (initialised in lifespan) ────────────────────────────────
app = FastAPI(title="Doorbell MJPEG Proxy")

_latest_frame = None  # bytes or None
_frame_count = 0
_condition = None  # asyncio.Condition, created in lifespan
_overlay = None  # DoorbellOverlay, created in lifespan

# Thread pool for CPU-bound PIL compose (keeps event loop responsive)
_compose_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)


# ── Overlay ───────────────────────────────────────────────────────────────

def _load_font(size):
    """Load SFNS font with fallback."""
    for path in [FONT_PATH_SFNS, FONT_PATH_FALLBACK]:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


class DoorbellOverlay:
    """Pre-rendered doorbell UI template with fast per-frame composition."""

    def __init__(self):
        self.template = None  # PIL Image
        self.camera_y = 0
        self.camera_h = 0
        self.corner_mask = None
        self._build()

    def _build(self):
        canvas = Image.new("RGB", (OUTPUT_WIDTH, OUTPUT_HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(canvas)

        font_header = _load_font(HEADER_FONT_SIZE)
        font_name = _load_font(NAME_FONT_SIZE)
        font_sub = _load_font(SUBTITLE_FONT_SIZE)

        # ── Header: "Tring tring" with bell icons ──
        header_text = "Tring tring"
        bbox = draw.textbbox((0, 0), header_text, font=font_header)
        header_w = bbox[2] - bbox[0]
        header_h = bbox[3] - bbox[1]
        header_x = (OUTPUT_WIDTH - header_w) // 2
        header_y = TEXT_PADDING

        draw.text((header_x, header_y), header_text, fill=HEADER_COLOR, font=font_header)

        # Bell icons on either side
        # bell_size = 48
        # bell_y = header_y + (header_h - bell_size) // 2
        # self._draw_bell(draw, header_x - bell_size - 24, bell_y, bell_size, BELL_COLOR)
        # self._draw_bell(draw, header_x + header_w + 24, bell_y, bell_size, BELL_COLOR)

        # ── Person section (bottom) ──
        person_y = OUTPUT_HEIGHT - TEXT_PADDING - AVATAR_SIZE
        avatar_x = TEXT_PADDING

        # Circular avatar placeholder
        draw.ellipse(
            [avatar_x, person_y, avatar_x + AVATAR_SIZE, person_y + AVATAR_SIZE],
            fill=AVATAR_BG,
        )
        # Simple person silhouette
        cx = avatar_x + AVATAR_SIZE // 2
        cy = person_y + AVATAR_SIZE // 2
        head_r = AVATAR_SIZE // 7
        draw.ellipse(
            [cx - head_r, cy - head_r - 10, cx + head_r, cy + head_r - 10],
            fill=AVATAR_FG,
        )
        draw.chord(
            [cx - head_r * 2, cy + 2, cx + head_r * 2, cy + AVATAR_SIZE // 2 + 4],
            180, 360,
            fill=AVATAR_FG,
        )

        # Name + subtitle
        text_x = avatar_x + AVATAR_SIZE + 40
        name = "Onbekend"
        subtitle = "Gezichtsherkenning niet actief"

        nb = draw.textbbox((0, 0), name, font=font_name)
        sb = draw.textbbox((0, 0), subtitle, font=font_sub)
        name_h = nb[3] - nb[1]
        sub_h = sb[3] - sb[1]
        total_text_h = name_h + 25 + sub_h
        ty = person_y + (AVATAR_SIZE - total_text_h - 20) // 2

        draw.text((text_x, ty), name, fill=NAME_COLOR, font=font_name)
        draw.text((text_x, ty + name_h + 25), subtitle, fill=SUBTITLE_COLOR, font=font_sub)

        # ── Camera area (between header and person) ──
        self.camera_y = header_y + header_h + TEXT_PADDING
        camera_bottom = person_y - TEXT_PADDING
        self.camera_h = camera_bottom - self.camera_y

        # Rounded-corner mask
        self.corner_mask = Image.new("L", (CONTENT_WIDTH, self.camera_h), 0)
        mask_draw = ImageDraw.Draw(self.corner_mask)
        mask_draw.rounded_rectangle(
            [0, 0, CONTENT_WIDTH - 1, self.camera_h - 1],
            radius=CORNER_RADIUS,
            fill=255,
        )

        # Dark camera placeholder (visible before first frame)
        cam_bg = Image.new("RGB", (CONTENT_WIDTH, self.camera_h), CAMERA_BG)
        canvas.paste(cam_bg, (TEXT_PADDING, self.camera_y), self.corner_mask)

        self.template = canvas
        logger.info(
            f"Overlay ready: camera area {CONTENT_WIDTH}x{self.camera_h} at y={self.camera_y}"
        )

    @staticmethod
    def _draw_bell(draw, x, y, size, color):
        """Draw a simple bell icon at (x, y) with given size."""
        cx = x + size // 2
        # Dome (top half-ellipse)
        dome_w = int(size * 0.55)
        dome_h = int(size * 0.40)
        draw.pieslice(
            [cx - dome_w, y, cx + dome_w, y + dome_h * 2],
            180, 360,
            fill=color,
        )
        # Body (flared lower section)
        body_top = y + dome_h
        body_bot = y + int(size * 0.78)
        bw_top = dome_w
        bw_bot = int(size * 0.50)
        draw.polygon(
            [
                (cx - bw_top, body_top),
                (cx + bw_top, body_top),
                (cx + bw_bot, body_bot),
                (cx - bw_bot, body_bot),
            ],
            fill=color,
        )
        # Rim
        rim_y = body_bot
        draw.rounded_rectangle(
            [cx - bw_bot - 2, rim_y, cx + bw_bot + 2, rim_y + 4],
            radius=2,
            fill=color,
        )
        # Clapper
        cr = max(3, size // 12)
        draw.ellipse(
            [cx - cr, rim_y + 5, cx + cr, rim_y + 5 + cr * 2],
            fill=color,
        )
        # Handle arc at top
        hw = size // 8
        draw.arc(
            [cx - hw, y - int(size * 0.12), cx + hw, y + int(size * 0.08)],
            180, 360,
            fill=color,
            width=max(2, size // 16),
        )

    def compose(self, raw_jpeg):
        """Composite a camera frame onto the overlay template. Returns JPEG bytes."""
        try:
            cam = Image.open(io.BytesIO(raw_jpeg)).convert("RGB")
        except Exception:
            return raw_jpeg

        cam = cam.crop((0, 26, cam.width, cam.height - 28))
        cam_w, cam_h = cam.size
        tw, th = CONTENT_WIDTH, self.camera_h

        # Cover-crop: scale to fill, then center-crop
        scale = max(tw / cam_w, th / cam_h)
        new_w = int(cam_w * scale)
        new_h = int(cam_h * scale)
        cam = cam.resize((new_w, new_h), Image.BILINEAR)

        left = 0
        top = (new_h - th) // 2
        cam = cam.crop((left, top, left + tw, top + th))

        # Paste camera onto template copy with rounded corners
        frame = self.template.copy()
        frame.paste(cam, (TEXT_PADDING, self.camera_y), self.corner_mask)

        buf = io.BytesIO()
        frame.save(buf, format="JPEG", quality=80)
        return buf.getvalue()


# ── Frame buffer ──────────────────────────────────────────────────────────

async def _push_frame(jpeg_bytes):
    global _latest_frame, _frame_count
    async with _condition:
        _latest_frame = jpeg_bytes
        _frame_count += 1
        _condition.notify_all()


async def _wait_for_frame(last_count):
    """Wait for a new frame. Returns (jpeg_bytes, frame_count)."""
    async with _condition:
        while _frame_count == last_count or _latest_frame is None:
            await _condition.wait()
        return _latest_frame, _frame_count


# ── ffmpeg reader ─────────────────────────────────────────────────────────

async def ffmpeg_reader(url, transport, raw):
    """Run ffmpeg and push composed frames to the shared buffer."""
    while True:
        process = None
        try:
            cmd = [
                "ffmpeg",
                "-rtsp_transport", transport,
                "-fflags", "nobuffer+discardcorrupt",
                "-flags", "low_delay",
                "-probesize", "32",
                "-analyzeduration", "0",
                "-reorder_queue_size", "0",
                "-max_delay", "0",
                "-i", url,
            ]
            if not raw:
                # Crop watermark (top 60px), scale to content width, limit FPS
                vf = f"crop=in_w:in_h-60:0:60,scale={CONTENT_WIDTH}:-2,fps={TARGET_FPS}"
                cmd += ["-vf", vf]
            cmd += [
                "-f", "image2pipe",
                "-vcodec", "mjpeg",
                "-q:v", "5",
                "-fps_mode", "drop",
                "-flush_packets", "1",
                "-threads", "2",
                "-",
            ]

            logger.info(f"Starting ffmpeg: {transport} → {url}")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Drain stderr in background
            async def drain():
                async for line in process.stderr:
                    text = line.decode(errors="replace").rstrip()
                    if any(kw in text.lower() for kw in ["error", "fail", "refused"]):
                        logger.warning(f"ffmpeg: {text}")

            stderr_task = asyncio.create_task(drain())

            buf = bytearray()
            frames = 0
            t_start = time.monotonic()
            compose_ms_total = 0.0

            while True:
                chunk = await process.stdout.read(65536)
                if not chunk:
                    break

                buf.extend(chunk)

                while True:
                    soi = buf.find(b"\xff\xd8")
                    if soi == -1:
                        buf.clear()
                        break
                    eoi = buf.find(b"\xff\xd9", soi + 2)
                    if eoi == -1:
                        if soi > 0:
                            del buf[:soi]
                        break

                    raw_jpeg = bytes(buf[soi:eoi + 2])
                    del buf[:eoi + 2]
                    frames += 1

                    # Compose overlay (offloaded to thread pool)
                    if _overlay and not raw:
                        loop = asyncio.get_event_loop()
                        t0 = time.monotonic()
                        composed = await loop.run_in_executor(
                            _compose_pool, _overlay.compose, raw_jpeg
                        )
                        compose_ms_total += (time.monotonic() - t0) * 1000
                        await _push_frame(composed)
                    else:
                        await _push_frame(raw_jpeg)

                    if frames == 1:
                        elapsed = time.monotonic() - t_start
                        logger.info(
                            f"First frame: {len(raw_jpeg):,}b raw → "
                            f"{len(composed) if _overlay and not raw else len(raw_jpeg):,}b composed, "
                            f"{elapsed:.1f}s"
                        )
                    elif frames % 100 == 0:
                        elapsed = time.monotonic() - t_start
                        avg_ms = compose_ms_total / frames
                        logger.info(
                            f"{frames} frames, {frames / elapsed:.1f} FPS, "
                            f"compose avg {avg_ms:.0f}ms"
                        )

            stderr_task.cancel()
            logger.warning(
                f"ffmpeg exited (code={process.returncode}), {frames} frames total"
            )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"ffmpeg error: {e}")
        finally:
            if process and process.returncode is None:
                process.kill()
                await process.wait()

        logger.info("Reconnecting in 2s...")
        await asyncio.sleep(2.0)


# ── Routes ────────────────────────────────────────────────────────────────

async def mjpeg_generator():
    last_count = -1
    boundary = b"frame"
    while True:
        jpeg_bytes, last_count = await _wait_for_frame(last_count)
        yield (
            b"--" + boundary + b"\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(jpeg_bytes)).encode() + b"\r\n"
            b"\r\n" + jpeg_bytes + b"\r\n"
        )


@app.get("/stream")
async def stream():
    return StreamingResponse(
        mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/health")
async def health():
    return {"status": "ok", "frames": _frame_count}


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Styled doorbell MJPEG proxy")
    parser.add_argument("--url", default=DEFAULT_URL, help="RTSP URL")
    parser.add_argument("--transport", default="udp", choices=["udp", "tcp"])
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--raw", action="store_true", help="Skip overlay, raw passthrough")
    args = parser.parse_args()

    import uvicorn
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app):
        global _condition, _overlay
        # Create Condition inside the running event loop (Python 3.9 compat)
        _condition = asyncio.Condition()
        if not args.raw:
            _overlay = DoorbellOverlay()
        task = asyncio.create_task(ffmpeg_reader(args.url, args.transport, args.raw))
        logger.info(f"Doorbell proxy on http://0.0.0.0:{args.port}/stream")
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    app.router.lifespan_context = lifespan

    print(f"Doorbell MJPEG proxy → http://0.0.0.0:{args.port}/stream")
    print(f"RTSP: {args.url}")
    print(f"Transport: {args.transport}, Overlay: {'off (raw)' if args.raw else 'on'}")
    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()

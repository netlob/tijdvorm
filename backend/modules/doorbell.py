"""Doorbell camera feed — reads RTSP stream via ffmpeg, composites a styled
overlay (header, rounded camera feed, person info), and pushes JPEG frames
to the shared FrameBuffer.
"""

import asyncio
import concurrent.futures
import io
import logging

from PIL import Image, ImageDraw, ImageFont

from backend.config import (
    NVR_RTSP_URL, OUTPUT_WIDTH, OUTPUT_HEIGHT, FONT_PATH,
    DOORBELL_FPS, DOORBELL_PADDING, DOORBELL_CONTENT_WIDTH,
    DOORBELL_CORNER_RADIUS, DOORBELL_BG, DOORBELL_HEADER_COLOR,
    DOORBELL_NAME_COLOR, DOORBELL_SUBTITLE_COLOR,
    DOORBELL_AVATAR_BG, DOORBELL_AVATAR_FG, DOORBELL_CAMERA_BG,
    DOORBELL_HEADER_FONT_SIZE, DOORBELL_NAME_FONT_SIZE,
    DOORBELL_SUBTITLE_FONT_SIZE, DOORBELL_AVATAR_SIZE,
)

logger = logging.getLogger("tijdvorm.doorbell")

# Thread pool for CPU-bound PIL composition (keeps event loop responsive)
_compose_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)

# ffmpeg filter: crop watermark, scale to content width, limit FPS
_VIDEO_FILTER = (
    f"crop=in_w:in_h-60:0:60,"
    f"scale={DOORBELL_CONTENT_WIDTH}:-2,"
    f"fps={DOORBELL_FPS}"
)


# ── Font helper ───────────────────────────────────────────────────────────

def _load_font(size):
    """Load SFNS font, fall back to Pillow default."""
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except (OSError, IOError):
        logger.warning(f"Could not load {FONT_PATH}, using default font")
        return ImageFont.load_default()


# ── Overlay ───────────────────────────────────────────────────────────────

class DoorbellOverlay:
    """Pre-rendered doorbell UI template with fast per-frame composition.

    The static parts (background, header, person section) are rendered once.
    Each incoming camera frame is resized, given rounded corners, and pasted
    onto a copy of the template.
    """

    def __init__(self):
        self.template = None   # PIL Image
        self.camera_y = 0
        self.camera_h = 0
        self.corner_mask = None
        self._build()

    def _build(self):
        pad = DOORBELL_PADDING
        cw = DOORBELL_CONTENT_WIDTH

        canvas = Image.new("RGB", (OUTPUT_WIDTH, OUTPUT_HEIGHT), DOORBELL_BG)
        draw = ImageDraw.Draw(canvas)

        font_header = _load_font(DOORBELL_HEADER_FONT_SIZE)
        font_name = _load_font(DOORBELL_NAME_FONT_SIZE)
        font_sub = _load_font(DOORBELL_SUBTITLE_FONT_SIZE)

        # ── Header ──
        header_text = "Tring tring"
        bbox = draw.textbbox((0, 0), header_text, font=font_header)
        header_w = bbox[2] - bbox[0]
        header_h = bbox[3] - bbox[1]
        header_x = (OUTPUT_WIDTH - header_w) // 2
        header_y = pad

        draw.text((header_x, header_y), header_text, fill=DOORBELL_HEADER_COLOR, font=font_header)

        # ── Person section (bottom) ──
        avatar_size = DOORBELL_AVATAR_SIZE
        person_y = OUTPUT_HEIGHT - pad - avatar_size
        avatar_x = pad

        # Circular avatar placeholder
        draw.ellipse(
            [avatar_x, person_y, avatar_x + avatar_size, person_y + avatar_size],
            fill=DOORBELL_AVATAR_BG,
        )
        # Person silhouette
        cx = avatar_x + avatar_size // 2
        cy = person_y + avatar_size // 2
        head_r = avatar_size // 7
        draw.ellipse(
            [cx - head_r, cy - head_r - 10, cx + head_r, cy + head_r - 10],
            fill=DOORBELL_AVATAR_FG,
        )
        draw.chord(
            [cx - head_r * 2, cy + 2, cx + head_r * 2, cy + avatar_size // 2 + 4],
            180, 360,
            fill=DOORBELL_AVATAR_FG,
        )

        # Name + subtitle
        text_x = avatar_x + avatar_size + 40
        name = "Onbekend"
        subtitle = "Gezichtsherkenning niet actief"

        nb = draw.textbbox((0, 0), name, font=font_name)
        sb = draw.textbbox((0, 0), subtitle, font=font_sub)
        name_h = nb[3] - nb[1]
        sub_h = sb[3] - sb[1]
        total_text_h = name_h + 25 + sub_h
        ty = person_y + (avatar_size - total_text_h - 20) // 2

        draw.text((text_x, ty), name, fill=DOORBELL_NAME_COLOR, font=font_name)
        draw.text((text_x, ty + name_h + 25), subtitle, fill=DOORBELL_SUBTITLE_COLOR, font=font_sub)

        # ── Camera area (between header and person) ──
        self.camera_y = header_y + header_h + pad
        camera_bottom = person_y - pad
        self.camera_h = camera_bottom - self.camera_y

        # Rounded-corner mask
        self.corner_mask = Image.new("L", (cw, self.camera_h), 0)
        mask_draw = ImageDraw.Draw(self.corner_mask)
        mask_draw.rounded_rectangle(
            [0, 0, cw - 1, self.camera_h - 1],
            radius=DOORBELL_CORNER_RADIUS,
            fill=255,
        )

        # Dark camera placeholder (visible before first frame arrives)
        cam_bg = Image.new("RGB", (cw, self.camera_h), DOORBELL_CAMERA_BG)
        canvas.paste(cam_bg, (pad, self.camera_y), self.corner_mask)

        self.template = canvas
        logger.info(
            f"Doorbell overlay ready: camera {cw}x{self.camera_h} at y={self.camera_y}"
        )

    def compose(self, raw_jpeg):
        """Composite a camera frame onto the overlay. Returns JPEG bytes.

        Runs in a thread pool — must be thread-safe (only reads self.*).
        """
        try:
            cam = Image.open(io.BytesIO(raw_jpeg)).convert("RGB")
        except Exception:
            return raw_jpeg

        pad = DOORBELL_PADDING
        cw = DOORBELL_CONTENT_WIDTH

        # Crop residual watermark edges
        cam = cam.crop((0, 26, cam.width, cam.height - 28))
        cam_w, cam_h = cam.size
        tw, th = cw, self.camera_h

        # Cover-crop: scale to fill, then crop to fit
        scale = max(tw / cam_w, th / cam_h)
        new_w = int(cam_w * scale)
        new_h = int(cam_h * scale)
        cam = cam.resize((new_w, new_h), Image.BILINEAR)

        left = 0
        top = (new_h - th) // 2
        cam = cam.crop((left, top, left + tw, top + th))

        # Paste with rounded corners onto template copy
        frame = self.template.copy()
        frame.paste(cam, (pad, self.camera_y), self.corner_mask)

        buf = io.BytesIO()
        frame.save(buf, format="JPEG", quality=80)
        return buf.getvalue()


# Lazily initialised overlay singleton
_overlay = None


def _get_overlay():
    global _overlay
    if _overlay is None:
        _overlay = DoorbellOverlay()
    return _overlay


# ── RTSP reader loop ──────────────────────────────────────────────────────

async def doorbell_loop(frame_buffer, stop_event: asyncio.Event):
    """Read RTSP stream via ffmpeg subprocess, compose overlay, push to FrameBuffer.

    Uses TCP transport — required for Docker bridge networking (UDP RTSP
    negotiates random data ports that can't pass through Docker NAT).
    Reconnects automatically on stream failure.
    """
    logger.info("Doorbell RTSP stream starting")
    overlay = _get_overlay()
    loop = asyncio.get_event_loop()

    while not stop_event.is_set():
        process = None
        stderr_task = None
        try:
            cmd = [
                "ffmpeg",
                "-rtsp_transport", "tcp",
                "-fflags", "nobuffer+discardcorrupt",
                "-flags", "low_delay",
                "-probesize", "32",
                "-analyzeduration", "0",
                "-reorder_queue_size", "0",
                "-max_delay", "0",
                "-i", NVR_RTSP_URL,
                "-vf", _VIDEO_FILTER,
                "-f", "image2pipe",
                "-vcodec", "mjpeg",
                "-q:v", "5",
                "-fps_mode", "drop",
                "-flush_packets", "1",
                "-threads", "2",
                "-",
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Log ffmpeg stderr in background (info level so errors are visible)
            async def _drain_stderr():
                async for line in process.stderr:
                    text = line.decode(errors="replace").rstrip()
                    if any(kw in text.lower() for kw in ["error", "fail", "refused", "timeout"]):
                        logger.warning(f"ffmpeg: {text}")
                    else:
                        logger.info(f"ffmpeg: {text}")

            stderr_task = asyncio.create_task(_drain_stderr())

            buf = bytearray()
            frames_received = 0

            while not stop_event.is_set():
                chunk = await process.stdout.read(65536)
                if not chunk:
                    break

                buf.extend(chunk)

                # Extract complete JPEG frames (SOI=0xFFD8, EOI=0xFFD9)
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
                    frames_received += 1

                    # Compose overlay in thread pool
                    composed = await loop.run_in_executor(
                        _compose_pool, overlay.compose, raw_jpeg
                    )
                    await frame_buffer.push_frame(composed)

                    if frames_received == 1:
                        logger.info("First doorbell frame composed")
                    elif frames_received % 100 == 0:
                        logger.info(f"Doorbell: {frames_received} frames composed")

            logger.info(
                f"ffmpeg exited (code={process.returncode}), frames: {frames_received}"
            )

        except Exception as e:
            logger.error(f"RTSP stream error: {e}")
        finally:
            if process and process.returncode is None:
                process.kill()
                await process.wait()
            if stderr_task:
                stderr_task.cancel()

        if not stop_event.is_set():
            logger.warning("RTSP stream disconnected, reconnecting in 2s...")
            await asyncio.sleep(2.0)

    logger.info("Doorbell stream stopped")

"""Doorbell camera feed — reads RTSP stream via ffmpeg, composites a styled
overlay (header, rounded camera feed, person info), and pushes JPEG frames
to the shared FrameBuffer.

Hot path uses turbojpeg + numpy for 2-5× faster JPEG decode/encode and
array-based composition instead of PIL per-frame copies.
"""

import asyncio
import concurrent.futures
import logging
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from turbojpeg import TurboJPEG, TJPF_RGB

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

_tj = TurboJPEG()

# Thread pool for CPU-bound composition (keeps event loop responsive)
_compose_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)

# ffmpeg filter: crop watermark, scale to content width.
# NO fps filter — it buffers frames by timestamp and adds 10-20s latency
# on live RTSP streams.  Rate-limiting is done in Python instead.
_VIDEO_FILTER = f"crop=in_w:in_h-60:0:60,scale={DOORBELL_CONTENT_WIDTH}:-2"

# Minimum interval between pushed frames (Python-side rate limit)
_FRAME_INTERVAL = 1.0 / DOORBELL_FPS  # 0.2s for 5 FPS


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

    The static parts (background, header, person section) are rendered once
    via PIL, then converted to numpy arrays.  Each incoming camera frame is
    decoded with turbojpeg, resized, masked, and composited in numpy, then
    re-encoded with turbojpeg — 2-5× faster than the pure-PIL path.
    """

    def __init__(self):
        self._template_np = None   # numpy uint8 (H, W, 3) RGB
        self._mask_3d = None       # numpy bool  (cam_h, cw, 3)
        self.camera_y = 0
        self.camera_h = 0
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

        # Rounded-corner mask (PIL for drawing, then convert to numpy)
        corner_mask_pil = Image.new("L", (cw, self.camera_h), 0)
        mask_draw = ImageDraw.Draw(corner_mask_pil)
        mask_draw.rounded_rectangle(
            [0, 0, cw - 1, self.camera_h - 1],
            radius=DOORBELL_CORNER_RADIUS,
            fill=255,
        )

        # Dark camera placeholder (visible before first frame arrives)
        cam_bg = Image.new("RGB", (cw, self.camera_h), DOORBELL_CAMERA_BG)
        canvas.paste(cam_bg, (pad, self.camera_y), corner_mask_pil)

        # ── Convert to numpy for fast per-frame composition ──
        self._template_np = np.array(canvas)                          # (H, W, 3) uint8
        mask_2d = np.array(corner_mask_pil) > 0                       # (cam_h, cw) bool
        self._mask_3d = np.repeat(mask_2d[:, :, np.newaxis], 3, axis=2)  # (cam_h, cw, 3)

        logger.info(
            f"Doorbell overlay ready: camera {cw}x{self.camera_h} at y={self.camera_y}"
        )

    def compose(self, raw_jpeg):
        """Composite a camera frame onto the overlay. Returns JPEG bytes.

        Runs in a thread pool — must be thread-safe (only reads self.*).
        Uses turbojpeg decode/encode + numpy array ops for speed.
        """
        try:
            cam = _tj.decode(raw_jpeg, pixel_format=TJPF_RGB)
        except Exception:
            return raw_jpeg

        pad = DOORBELL_PADDING
        cw = DOORBELL_CONTENT_WIDTH

        # Crop residual watermark edges (numpy slice — zero-copy)
        cam = cam[26:cam.shape[0] - 28, :, :]
        cam_h, cam_w = cam.shape[:2]
        tw, th = cw, self.camera_h

        # Cover-crop: scale to fill, then crop to fit
        scale = max(tw / cam_w, th / cam_h)
        new_w = int(cam_w * scale)
        new_h = int(cam_h * scale)
        # PIL resize for quality bilinear interpolation (still C code)
        cam = np.asarray(
            Image.fromarray(cam).resize((new_w, new_h), Image.BILINEAR)
        )

        left = 0
        top = (new_h - th) // 2
        cam = cam[top:top + th, left:left + tw, :]

        # Paste with rounded corners onto template copy (numpy — fast)
        frame = self._template_np.copy()
        region = frame[self.camera_y:self.camera_y + th, pad:pad + cw]
        np.copyto(region, cam, where=self._mask_3d)

        # Encode to JPEG via turbojpeg (2-5× faster than PIL)
        return _tj.encode(frame, pixel_format=TJPF_RGB, quality=80)


# Lazily initialised overlay singleton
_overlay = None


def _get_overlay():
    global _overlay
    if _overlay is None:
        _overlay = DoorbellOverlay()
    return _overlay


# ── RTSP reader loop ──────────────────────────────────────────────────────
#
# Architecture: two concurrent async tasks prevent pipe backpressure.
#
#   _pipe_reader  — drains ffmpeg stdout as fast as possible, always
#                   overwrites `latest_raw` with the newest JPEG frame.
#                   Never blocks on compose/push, so ffmpeg never stalls.
#
#   _compose_loop — wakes every 1/FPS seconds, grabs whatever is in
#                   `latest_raw`, composites the overlay, and pushes to
#                   the FrameBuffer.
#
# This prevents the growing-delay problem: ffmpeg outputs ~12 FPS but the
# pipe reader keeps up because it does zero processing.  The compose loop
# independently picks up the latest frame at 5 FPS.


async def _pipe_reader(process, stop_event, state):
    """Drain ffmpeg stdout as fast as possible — never block on processing."""
    buf = bytearray()

    while not stop_event.is_set():
        chunk = await process.stdout.read(131072)
        if not chunk:
            break

        buf.extend(chunk)

        # Extract all complete JPEG frames, keep only the latest
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

            jpeg = bytes(buf[soi:eoi + 2])
            del buf[:eoi + 2]
            state["latest"] = jpeg
            state["received"] += 1


async def _compose_loop(overlay, frame_buffer, stop_event, state):
    """Compose overlay at target FPS and push to FrameBuffer."""
    loop = asyncio.get_event_loop()
    last_raw = None
    pushed = 0

    while not stop_event.is_set():
        t0 = time.monotonic()

        raw = state["latest"]
        if raw is not None and raw is not last_raw:
            last_raw = raw
            composed = await loop.run_in_executor(
                _compose_pool, overlay.compose, raw
            )
            await frame_buffer.push_frame(composed)
            pushed += 1

            if pushed == 1:
                logger.info("First doorbell frame composed")
            elif pushed % 100 == 0:
                logger.info(
                    f"Doorbell: {pushed} pushed "
                    f"({state['received']} received from ffmpeg)"
                )

        # Sleep remainder of frame interval
        elapsed = time.monotonic() - t0
        await asyncio.sleep(max(0.01, _FRAME_INTERVAL - elapsed))


async def doorbell_loop(frame_buffer, stop_event: asyncio.Event):
    """Read RTSP stream via ffmpeg, compose overlay, push to FrameBuffer.

    Uses UDP transport for lowest latency — old buffered packets are simply
    lost so we start from the live edge immediately.  Requires host networking
    (network_mode: host) so UDP ports aren't blocked by Docker NAT.
    Reconnects automatically on stream failure.
    """
    logger.info("Doorbell RTSP stream starting")
    overlay = _get_overlay()

    while not stop_event.is_set():
        process = None
        stderr_task = None
        reader_task = None
        compose_task = None
        try:
            cmd = [
                "ffmpeg",
                "-rtsp_transport", "udp",
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

            # Log ffmpeg stderr in background
            async def _drain_stderr():
                async for line in process.stderr:
                    text = line.decode(errors="replace").rstrip()
                    if any(kw in text.lower() for kw in ["error", "fail", "refused", "timeout"]):
                        logger.warning(f"ffmpeg: {text}")
                    else:
                        logger.info(f"ffmpeg: {text}")

            # Shared state between reader and composer (single-threaded, no lock needed)
            state = {"latest": None, "received": 0}

            stderr_task = asyncio.create_task(_drain_stderr())
            reader_task = asyncio.create_task(
                _pipe_reader(process, stop_event, state)
            )
            compose_task = asyncio.create_task(
                _compose_loop(overlay, frame_buffer, stop_event, state)
            )

            # Wait for pipe reader to finish (ffmpeg closed stdout)
            await reader_task

            logger.info(
                f"ffmpeg exited (code={process.returncode}), "
                f"frames received: {state['received']}"
            )

        except Exception as e:
            logger.error(f"RTSP stream error: {e}")
        finally:
            # Kill ffmpeg — shield from cancellation so we don't leave zombies
            if process and process.returncode is None:
                process.kill()
                try:
                    await asyncio.shield(process.wait())
                except (asyncio.CancelledError, Exception):
                    pass  # process is killed, best effort
            for t in [stderr_task, reader_task, compose_task]:
                if t and not t.done():
                    t.cancel()

        if not stop_event.is_set():
            logger.warning("RTSP stream disconnected, reconnecting in 2s...")
            await asyncio.sleep(2.0)

    logger.info("Doorbell stream stopped")

"""Doorbell camera feed — fetches NVR snapshots and pushes to FrameBuffer."""

import asyncio
import io
import logging
import time

import httpx
from PIL import Image

from backend.config import NVR_SNAPSHOT_URL, DOORBELL_FPS, OUTPUT_WIDTH, OUTPUT_HEIGHT

logger = logging.getLogger("tijdvorm.doorbell")


def _process_and_encode(raw_bytes: bytes) -> bytes | None:
    """Crop, resize, and JPEG-encode an NVR snapshot. Runs in thread pool."""
    try:
        img = Image.open(io.BytesIO(raw_bytes))
        w, h = img.size

        # Crop top 60px (camera timestamp bar)
        img = img.crop((0, 60, w, h))
        w, h = img.size

        # Resize so height = OUTPUT_HEIGHT (BILINEAR is much faster than LANCZOS)
        ratio = OUTPUT_HEIGHT / h
        new_width = int(w * ratio)
        img = img.resize((new_width, OUTPUT_HEIGHT), Image.Resampling.BILINEAR)

        # Crop to OUTPUT_WIDTH, aligned left
        img = img.crop((0, 0, OUTPUT_WIDTH, OUTPUT_HEIGHT))

        # Encode to JPEG
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"Snapshot processing failed: {e}")
        return None


async def doorbell_loop(frame_buffer, stop_event: asyncio.Event):
    """Continuously fetch camera snapshots and push to the frame buffer.

    Runs until stop_event is set.
    """
    interval = 1.0 / DOORBELL_FPS
    logger.info(f"Doorbell stream started ({DOORBELL_FPS} FPS)")

    loop = asyncio.get_running_loop()

    async with httpx.AsyncClient(timeout=3.0) as client:
        while not stop_event.is_set():
            start = time.monotonic()
            try:
                resp = await client.get(NVR_SNAPSHOT_URL)
                resp.raise_for_status()

                # Offload CPU-bound image processing to thread pool
                jpeg_bytes = await loop.run_in_executor(
                    None, _process_and_encode, resp.content
                )
                if jpeg_bytes:
                    await frame_buffer.push_frame(jpeg_bytes)

            except Exception as e:
                logger.warning(f"Doorbell frame error: {e}")

            # Sleep only the remaining time to hit target FPS
            elapsed = time.monotonic() - start
            remaining = interval - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)

    logger.info("Doorbell stream stopped")

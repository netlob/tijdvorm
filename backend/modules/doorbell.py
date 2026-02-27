"""Doorbell camera feed — fetches NVR snapshots and pushes to FrameBuffer."""

import asyncio
import io
import logging

import httpx
from PIL import Image

from backend.config import NVR_SNAPSHOT_URL, DOORBELL_FPS, OUTPUT_WIDTH, OUTPUT_HEIGHT

logger = logging.getLogger("tijdvorm.doorbell")


def _process_snapshot(raw_bytes: bytes) -> Image.Image | None:
    """Crop and resize NVR snapshot to portrait format."""
    try:
        img = Image.open(io.BytesIO(raw_bytes))
        w, h = img.size

        # Crop top 60px (camera timestamp bar)
        img = img.crop((0, 60, w, h))
        w, h = img.size

        # Resize so height = OUTPUT_HEIGHT
        ratio = OUTPUT_HEIGHT / h
        new_width = int(w * ratio)
        img = img.resize((new_width, OUTPUT_HEIGHT), Image.Resampling.LANCZOS)

        # Crop to OUTPUT_WIDTH, aligned left
        img = img.crop((0, 0, OUTPUT_WIDTH, OUTPUT_HEIGHT))
        return img
    except Exception as e:
        logger.warning(f"Snapshot processing failed: {e}")
        return None


async def doorbell_loop(frame_buffer, stop_event: asyncio.Event):
    """Continuously fetch camera snapshots and push to the frame buffer.

    Runs until stop_event is set.
    """
    interval = 1.0 / DOORBELL_FPS
    logger.info(f"Doorbell stream started ({DOORBELL_FPS} FPS)")

    async with httpx.AsyncClient(timeout=5.0) as client:
        while not stop_event.is_set():
            try:
                resp = await client.get(NVR_SNAPSHOT_URL)
                resp.raise_for_status()

                img = _process_snapshot(resp.content)
                if img:
                    # Encode to JPEG
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=85)
                    await frame_buffer.push_frame(buf.getvalue())

            except Exception as e:
                logger.warning(f"Doorbell frame error: {e}")

            await asyncio.sleep(interval)

    logger.info("Doorbell stream stopped")

"""Main image generation loop — runs as a background asyncio task.

Polls Home Assistant state every second:
- TV active → idle / resume
- Doorbell active → start / stop camera feed
- Sauna / override changes → force immediate regeneration

Timeform mode pushes 1 FPS with a live seconds clock by caching the
expensive browser-rendered base and re-compositing the time overlay
every second.
"""

import asyncio
import io
import json
import logging
import os
import random
import time

import numpy as np
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont
from turbojpeg import TurboJPEG, TJPF_RGB

from backend.config import (
    UPDATE_INTERVAL_MINUTES, OUTPUT_WIDTH, OUTPUT_HEIGHT,
    LIVE_PREVIEW_PATH, LIVE_STATE_PATH, LIVE_DIR, FONT_PATH,
)
from backend.stream import FrameBuffer
from backend.integrations.home_assistant import (
    is_tv_active, is_doorbell_active, get_sauna_status,
    get_dryer_minutes_left,
)
from backend.modules import timeform, sauna, easter_eggs
from backend.modules.timeform import TimeformBase
from backend.modules.doorbell import doorbell_loop

logger = logging.getLogger("tijdvorm.generator")

_tj = TurboJPEG()

# Cached timeform base — set when timeform is the active mode,
# cleared when switching to another mode or going idle.
_tf_base: TimeformBase | None = None


def _image_to_jpeg(img: Image.Image, quality: int = 90) -> bytes:
    """Convert a PIL Image to JPEG bytes via turbojpeg (2-5× faster than PIL)."""
    if img.mode == "RGBA":
        img = img.convert("RGB")
    return _tj.encode(np.asarray(img), pixel_format=TJPF_RGB, quality=quality)


def _black_frame() -> bytes:
    """Generate a black 1080x1920 JPEG frame with 'First frame' text."""
    img = Image.new("RGB", (OUTPUT_WIDTH, OUTPUT_HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(FONT_PATH, 48)
    except (OSError, IOError):
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "First frame", font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((OUTPUT_WIDTH - text_w) / 2, (OUTPUT_HEIGHT - text_h) / 2),
        "First frame",
        fill=(255, 255, 255),
        font=font,
    )
    return _image_to_jpeg(img)


def _write_live_preview(jpeg_bytes: bytes, meta: dict):
    """Write live preview for the frontend."""
    try:
        os.makedirs(LIVE_DIR, exist_ok=True)

        tmp = LIVE_PREVIEW_PATH + ".tmp"
        with open(tmp, "wb") as f:
            f.write(jpeg_bytes)
        os.replace(tmp, LIVE_PREVIEW_PATH)

        state = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "type": meta.get("type"),
            "filename": meta.get("filename"),
            "url": "/live/preview.png",
        }
        tmp_state = LIVE_STATE_PATH + ".tmp"
        with open(tmp_state, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, sort_keys=True)
        os.replace(tmp_state, LIVE_STATE_PATH)
    except Exception as e:
        logger.warning(f"Live preview write failed: {e}")


async def _stop_doorbell(task: asyncio.Task | None, stop_event: asyncio.Event | None):
    """Gracefully stop the doorbell loop."""
    if stop_event:
        stop_event.set()
    if task and not task.done():
        try:
            await asyncio.wait_for(task, timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            task.cancel()
        except Exception:
            pass


async def _generate_frame(
    frame_buffer: FrameBuffer,
    override_path: str | None,
    sauna_status: dict | None,
    sauna_on: bool,
) -> None:
    """Run the priority chain and push a frame.

    When the timeform is selected, the expensive base is cached in _tf_base
    so subsequent seconds can re-composite cheaply.
    """
    global _tf_base

    frame_jpeg = None
    meta = {"type": None, "filename": None}

    # 1. Override
    if override_path:
        _tf_base = None
        try:
            img = Image.open(override_path)
            frame_jpeg = _image_to_jpeg(img)
            meta = {"type": "override", "filename": os.path.basename(override_path)}
            logger.info(f"Override: {meta['filename']}")
        except Exception as e:
            logger.warning(f"Override load failed: {e}")

    # 2. Easter egg roll
    if not frame_jpeg:
        settings = easter_eggs.load_settings()
        denom = settings.get("easter_egg_chance_denominator", 10)
        roll = False
        if denom <= 0:
            roll = False
        elif denom == 1:
            roll = True
        else:
            roll = random.randint(1, denom) == 1

        if roll:
            _tf_base = None
            egg_img = await easter_eggs.get_random_egg()
            if egg_img:
                frame_jpeg = _image_to_jpeg(egg_img)
                meta = {"type": "easteregg", "filename": "easter_egg"}
                logger.info("Easter egg selected")

    # 3. Sauna
    if not frame_jpeg and sauna_on:
        _tf_base = None
        img = await sauna.generate(sauna_status)
        if img:
            frame_jpeg = _image_to_jpeg(img)
            meta = {"type": "sauna", "filename": "sauna"}
            logger.info("Sauna image generated")

    # 4. Timeform (default) — cache the base for 1 FPS ticking
    if not frame_jpeg:
        base = await timeform.generate_base()
        if base:
            _tf_base = base
            img = timeform.compose_frame(base)
            frame_jpeg = _image_to_jpeg(img)
            meta = {"type": "timeform", "filename": "timeform"}
            logger.info("Timeform base generated")

    # Push to stream
    if frame_jpeg:
        await frame_buffer.push_frame(frame_jpeg)
        _write_live_preview(frame_jpeg, meta)
    else:
        logger.warning("All generators failed, no frame produced")


async def generation_loop(frame_buffer: FrameBuffer):
    """Main loop — polls HA every second, generates frames when needed.

    When timeform is the active mode, re-composites the cached base with
    the current HH:MM:SS every second (1 FPS live clock).
    """
    global _tf_base

    logger.info("Generation loop started")

    # Push initial black frame so MJPEG clients don't hang waiting
    await frame_buffer.push_frame(_black_frame())

    was_idle = False
    last_gen_time = 0.0
    last_second = -1          # track wall-clock second to push each exactly once

    # Doorbell task management
    db_task: asyncio.Task | None = None
    db_stop: asyncio.Event | None = None
    prev_db_active = False

    # State change tracking
    prev_override: str | None = None
    prev_sauna_on = False

    while True:
        try:
            # ── TV active check ──────────────────────────────────
            tv_active = await is_tv_active()

            if not tv_active and not was_idle:
                logger.info("TV inactive, ticking in background")
                # Stop doorbell if running
                if prev_db_active:
                    await _stop_doorbell(db_task, db_stop)
                    db_task = db_stop = None
                    prev_db_active = False
                was_idle = True

            if tv_active and was_idle:
                logger.info("TV active again, forcing regeneration")
                was_idle = False
                last_gen_time = 0  # Force full priority chain on wake

            # ── Doorbell check (TV active only) ───────────────────
            if tv_active:
                db_active = await is_doorbell_active()
            else:
                db_active = False

            if db_active and not prev_db_active:
                logger.info("Doorbell activated, starting camera feed")
                db_stop = asyncio.Event()
                db_task = asyncio.create_task(doorbell_loop(frame_buffer, db_stop))
            elif not db_active and prev_db_active:
                logger.info("Doorbell deactivated, stopping camera feed")
                await _stop_doorbell(db_task, db_stop)
                db_task = db_stop = None
                last_gen_time = 0  # Force immediate generation after doorbell
            prev_db_active = db_active

            if db_active:
                await asyncio.sleep(1)
                continue

            # ── State change detection (TV active only) ───────────
            dryer_min = await get_dryer_minutes_left()

            if tv_active:
                override_path = easter_eggs.get_override_path()
                sauna_status = await get_sauna_status()
                sauna_on = bool(sauna_status and sauna_status.get("is_on"))
            else:
                override_path = prev_override
                sauna_status = None
                sauna_on = prev_sauna_on

            force = False
            if override_path != prev_override:
                logger.info(f"Override changed: {override_path}")
                force = True
            if sauna_on != prev_sauna_on:
                logger.info(f"Sauna state changed: {'on' if sauna_on else 'off'}")
                force = True
            prev_override = override_path
            prev_sauna_on = sauna_on

            # ── Generate / tick ──────────────────────────────────
            now = time.time()
            interval = UPDATE_INTERVAL_MINUTES * 60

            if tv_active and (force or (now - last_gen_time >= interval)):
                # Full regeneration with priority chain (override → egg → sauna → timeform)
                await _generate_frame(frame_buffer, override_path, sauna_status, sauna_on)
                last_gen_time = time.time()
            elif _tf_base is None:
                # No cached base yet (first run) — generate one even if TV is off
                base = await timeform.generate_base()
                if base:
                    _tf_base = base
                    last_gen_time = time.time()
                    logger.info("Initial timeform base generated")
            elif _tf_base is not None:
                # Tick cached base — always runs (TV on or off) for instant wake
                cur_second = int(time.time())
                if cur_second != last_second:
                    last_second = cur_second
                    img = timeform.compose_frame(_tf_base, dryer_minutes=dryer_min)
                    jpeg = _image_to_jpeg(img)
                    await frame_buffer.push_frame(jpeg)

        except Exception as e:
            logger.error(f"Generation cycle error: {e}", exc_info=True)

        # ── Wall-clock aligned sleep ──────────────────────────────
        # Sleep until 30ms past the next whole second so strftime
        # always returns the new value.  This prevents drift and
        # ensures each second is displayed exactly once.
        now = time.time()
        next_second = (now // 1) + 1.03
        await asyncio.sleep(max(0.05, next_second - now))

"""Home Assistant webhook — doorbell on/off control."""

import asyncio
import logging

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.modules.doorbell import doorbell_loop

logger = logging.getLogger("tijdvorm.webhooks")

router = APIRouter(prefix="/api")

# Doorbell state
_doorbell_task: asyncio.Task | None = None
_doorbell_stop: asyncio.Event | None = None


def _get_frame_buffer():
    """Late import to avoid circular dependency."""
    from backend.stream import get_frame_buffer
    return get_frame_buffer()


async def _start_doorbell():
    global _doorbell_task, _doorbell_stop

    if _doorbell_task and not _doorbell_task.done():
        logger.info("Doorbell already active")
        return

    _doorbell_stop = asyncio.Event()
    fb = _get_frame_buffer()
    _doorbell_task = asyncio.create_task(doorbell_loop(fb, _doorbell_stop))
    logger.info("Doorbell started")


async def _stop_doorbell():
    global _doorbell_task, _doorbell_stop

    if _doorbell_stop:
        _doorbell_stop.set()

    if _doorbell_task and not _doorbell_task.done():
        try:
            await asyncio.wait_for(_doorbell_task, timeout=5)
        except asyncio.TimeoutError:
            _doorbell_task.cancel()
        except Exception:
            pass

    _doorbell_task = None
    _doorbell_stop = None
    logger.info("Doorbell stopped")


def is_doorbell_active() -> bool:
    return _doorbell_task is not None and not _doorbell_task.done()


@router.post("/ha")
async def ha_webhook(payload: dict[str, Any]):
    """
    Unified endpoint for Home Assistant automations.
    Payload: { "action": "doorbell_on" | "doorbell_off" }
    """
    action = payload.get("action")

    if action in ("doorbell", "doorbell_on"):
        await _start_doorbell()
        return {"ok": True, "status": "doorbell_active"}

    if action == "doorbell_off":
        await _stop_doorbell()
        return {"ok": True, "status": "doorbell_inactive"}

    raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

"""Home Assistant webhook — secondary trigger for doorbell.

The generator loop polls HA state every second and manages doorbell
start/stop automatically.  This webhook endpoint is kept for backward
compatibility but is no longer the primary mechanism.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger("tijdvorm.webhooks")

router = APIRouter(prefix="/api")


@router.post("/ha")
async def ha_webhook(payload: dict[str, Any]):
    """
    Receives events from Home Assistant automations.
    The generator polls HA booleans every 1s, so state changes are
    picked up automatically. This endpoint acknowledges the event.
    """
    action = payload.get("action")

    if action in ("doorbell", "doorbell_on"):
        logger.info("Webhook: doorbell_on received (generator polls HA state)")
        return {"ok": True, "status": "doorbell state polled by generator"}

    if action == "doorbell_off":
        logger.info("Webhook: doorbell_off received (generator polls HA state)")
        return {"ok": True, "status": "doorbell state polled by generator"}

    raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

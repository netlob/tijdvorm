"""Home Assistant integration — async API calls via httpx."""

import logging
import time

import httpx

from datetime import datetime, timezone

from backend.config import (
    HA_BASE_URL, HA_TOKEN, HA_EXPLICIT_ENTITY, HA_TIMEOUT_SECONDS,
    HA_CACHE_TTL_SECONDS, HA_SAUNA_ENTITY, HA_POWER_ENTITY,
    HA_TEMP_ENTITY, HA_DOORBELL_ACTIVE_ENTITY, HA_TV_ENTITY,
    HA_DRYER_ENTITY, HA_DRYER_JOB_STATE_ENTITY,
    HA_SAUNA_TEMP_ENTITY, HA_SAUNA_HUMIDITY_ENTITY,
)

logger = logging.getLogger("tijdvorm.ha")

# Module-level shared client (set by app.py on startup)
_client: httpx.AsyncClient | None = None

# Cache for explicit-allowed check
_ha_cache = {"value": None, "ts": 0.0}


def set_client(client: httpx.AsyncClient):
    global _client
    _client = client


def _headers() -> dict:
    return {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}


async def _get_state(entity_id: str) -> dict | None:
    if not HA_BASE_URL or not HA_TOKEN or not _client:
        return None
    try:
        resp = await _client.get(
            f"{HA_BASE_URL}/api/states/{entity_id}",
            headers=_headers(),
            timeout=HA_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.debug(f"HA state fetch failed for {entity_id}: {e}")
        return None


async def is_tv_active() -> bool:
    """Check if the TV display boolean is on."""
    data = await _get_state(HA_TV_ENTITY)
    if data is None:
        return True  # Default to active if HA unavailable
    return str(data.get("state", "")).lower() == "on"


async def ha_explicit_allowed() -> bool:
    """Check if explicit content is allowed. Cached for HA_CACHE_TTL_SECONDS."""
    now = time.time()
    if _ha_cache["value"] is not None and (now - _ha_cache["ts"]) < HA_CACHE_TTL_SECONDS:
        return bool(_ha_cache["value"])

    data = await _get_state(HA_EXPLICIT_ENTITY)
    if data is None:
        if _ha_cache["value"] is None:
            _ha_cache["value"] = False
            _ha_cache["ts"] = now
        return bool(_ha_cache["value"])

    allowed = str(data.get("state", "")).lower() == "on"
    _ha_cache["value"] = allowed
    _ha_cache["ts"] = now
    return allowed


async def is_doorbell_active() -> bool:
    """Check if doorbell is currently active."""
    data = await _get_state(HA_DOORBELL_ACTIVE_ENTITY)
    if data is None:
        return False
    return str(data.get("state", "")).lower() == "on"


async def get_sauna_status() -> dict | None:
    """Returns {is_on, current_temp, set_temp} or None."""
    data = await _get_state(HA_SAUNA_ENTITY)
    if data is None:
        return None
    if data.get("state") == "heat_cool":
        attrs = data.get("attributes", {})
        return {
            "is_on": True,
            "current_temp": attrs.get("current_temperature"),
            "set_temp": attrs.get("temperature"),
        }
    return None


async def get_power_usage() -> float | None:
    """Returns power in Watts (converted from kW)."""
    data = await _get_state(HA_POWER_ENTITY)
    if data is None:
        return None
    try:
        return float(data["state"]) * 1000.0
    except (KeyError, ValueError, TypeError):
        return None


async def get_home_temperature() -> float | None:
    """Returns home temperature in Celsius."""
    data = await _get_state(HA_TEMP_ENTITY)
    if data is None:
        return None
    try:
        return float(data["state"])
    except (KeyError, ValueError, TypeError):
        return None


async def get_sauna_sensor_temp() -> float | None:
    """Returns sauna air temperature from dedicated sensor."""
    data = await _get_state(HA_SAUNA_TEMP_ENTITY)
    if data is None:
        return None
    try:
        return float(data["state"])
    except (KeyError, ValueError, TypeError):
        return None


async def get_sauna_humidity() -> float | None:
    """Returns sauna air humidity percentage."""
    data = await _get_state(HA_SAUNA_HUMIDITY_ENTITY)
    if data is None:
        return None
    try:
        return float(data["state"])
    except (KeyError, ValueError, TypeError):
        return None


async def get_dryer_status() -> dict | None:
    """Returns {"job_state": str, "minutes_left": int | None} or None.

    Uses the dryer job state entity as the primary check — if the dryer
    job state is "none" or unavailable the dryer is considered off.
    The completion-time entity is only consulted for the ETA when the
    dryer is actually running.
    """
    job_data = await _get_state(HA_DRYER_JOB_STATE_ENTITY)
    if job_data is None:
        return None
    job_state = str(job_data.get("state", "")).lower().strip()
    if not job_state or job_state in ("unavailable", "unknown", "none"):
        return None

    minutes_left = None
    time_data = await _get_state(HA_DRYER_ENTITY)
    if time_data is not None:
        ts = time_data.get("state")
        if ts and ts not in ("unavailable", "unknown"):
            try:
                completion_dt = datetime.fromisoformat(ts)
                delta = (completion_dt - datetime.now(timezone.utc)).total_seconds() / 60.0
                if delta > 0:
                    minutes_left = int(delta)
            except (ValueError, TypeError):
                pass

    return {"job_state": job_state, "minutes_left": minutes_left}

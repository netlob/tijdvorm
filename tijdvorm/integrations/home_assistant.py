import requests
import time
from tijdvorm.config import (
    HA_BASE_URL, HA_TOKEN, HA_EXPLICIT_ENTITY, HA_TIMEOUT_SECONDS, 
    HA_CACHE_TTL_SECONDS, HA_SAUNA_ENTITY, HA_POWER_ENTITY, HA_TEMP_ENTITY
)

_ha_cache = {"value": None, "ts": 0.0}

def ha_explicit_allowed():
    """Returns True if HA explicit boolean is on; False otherwise. Cached for HA_CACHE_TTL_SECONDS."""
    now = time.time()
    if _ha_cache["value"] is not None and (now - _ha_cache["ts"]) < HA_CACHE_TTL_SECONDS:
        return bool(_ha_cache["value"])

    if not HA_BASE_URL or not HA_TOKEN:
        # Not configured -> default to False (safe)
        _ha_cache["value"] = False
        _ha_cache["ts"] = now
        return False

    url = f"{HA_BASE_URL}/api/states/{HA_EXPLICIT_ENTITY}"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
            timeout=HA_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        state = data.get("state")
        allowed = str(state).lower() == "on"
        _ha_cache["value"] = allowed
        _ha_cache["ts"] = now
        return allowed
    except Exception as e:
        print(f"Warning: HA explicit check failed ({e}); treating as OFF")
        # If we had a cached value, keep it; else default False
        if _ha_cache["value"] is None:
            _ha_cache["value"] = False
            _ha_cache["ts"] = now
        return bool(_ha_cache["value"])

def get_sauna_status():
    """
    Fetches the status of the sauna climate entity.
    Returns a dict with 'is_on', 'current_temp', 'set_temp' or None if failed/off.
    """
    if not HA_BASE_URL or not HA_TOKEN:
        print("Warning: HA_BASE_URL or HA_TOKEN not set. Skipping sauna check.")
        return None

    url = f"{HA_BASE_URL}/api/states/{HA_SAUNA_ENTITY}"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
            timeout=HA_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        
        # Debug logs
        # print(f"Sauna data raw: {data}")
        
        state = data.get("state")
        attributes = data.get("attributes", {})
        
        is_on = state == "heat_cool"
        if is_on:
             return {
                 "is_on": True,
                 "current_temp": attributes.get("current_temperature"),
                 "set_temp": attributes.get("temperature")
             }
        print(f"Sauna is not on (state: {state})")
        return None

    except Exception as e:
        print(f"Warning: HA sauna check failed ({e})")
        return None

def get_power_usage():
    """
    Fetches the power consumed sensor.
    Returns float Watts (converted from kW if needed) or None.
    """
    if not HA_BASE_URL or not HA_TOKEN:
        return None

    url = f"{HA_BASE_URL}/api/states/{HA_POWER_ENTITY}"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
            timeout=HA_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        
        state = data.get("state")
        try:
            val = float(state)
            # Assuming kW based on user prompt, convert to W
            return val * 1000.0
        except Exception:
            return None
            
    except Exception as e:
        print(f"Warning: HA power check failed ({e})")
        return None

def get_home_temperature():
    """
    Fetches the home assistant temperature entity.
    Returns float (degrees C) or None.
    """
    if not HA_BASE_URL or not HA_TOKEN:
        return None

    url = f"{HA_BASE_URL}/api/states/{HA_TEMP_ENTITY}"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
            timeout=HA_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        
        state = data.get("state")
        try:
            val = float(state)
            return val
        except Exception:
            return None
            
    except Exception as e:
        print(f"Warning: HA temperature check failed ({e})")
        return None


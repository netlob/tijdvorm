"""Easter egg image management — manifest, override, weighted random selection."""

import json
import logging
import os
import random

from PIL import Image

from backend.config import (
    EASTER_EGGS_DIR, EASTER_EGGS_MANIFEST, EASTER_EGGS_OVERRIDE,
    EASTER_EGGS_SETTINGS,
)
from backend.integrations.home_assistant import ha_explicit_allowed

logger = logging.getLogger("tijdvorm.easter_eggs")


def load_manifest() -> dict:
    try:
        if not os.path.exists(EASTER_EGGS_MANIFEST):
            return {"version": 1, "images": {}}
        with open(EASTER_EGGS_MANIFEST, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"version": 1, "images": {}}
        data.setdefault("version", 1)
        data.setdefault("images", {})
        if not isinstance(data["images"], dict):
            data["images"] = {}
        return data
    except Exception:
        return {"version": 1, "images": {}}


def save_manifest(manifest: dict):
    os.makedirs(EASTER_EGGS_DIR, exist_ok=True)
    tmp = EASTER_EGGS_MANIFEST + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)
        os.replace(tmp, EASTER_EGGS_MANIFEST)
    except Exception as e:
        logger.warning(f"Failed to save manifest: {e}")


def get_override_path() -> str | None:
    """Returns absolute path to override image, or None."""
    try:
        if not os.path.exists(EASTER_EGGS_OVERRIDE):
            return None
        with open(EASTER_EGGS_OVERRIDE, "r", encoding="utf-8") as f:
            data = json.load(f)
        filename = data.get("filename") if isinstance(data, dict) else None
        if not filename or not isinstance(filename, str):
            return None
        path = os.path.join(EASTER_EGGS_DIR, os.path.basename(filename))
        if not os.path.exists(path):
            return None
        return os.path.abspath(path)
    except Exception:
        return None


def load_settings() -> dict:
    defaults = {"easter_egg_chance_denominator": 10}
    try:
        if not os.path.exists(EASTER_EGGS_SETTINGS):
            return defaults
        with open(EASTER_EGGS_SETTINGS, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return defaults
        denom = int(data.get("easter_egg_chance_denominator", 10))
        return {"easter_egg_chance_denominator": max(0, denom)}
    except Exception:
        return defaults


def _get_candidates() -> tuple[list[str], set | None, set, dict]:
    """Returns (files, enabled_set, explicit_set, priority_map)."""
    try:
        files = [
            f for f in os.listdir(EASTER_EGGS_DIR)
            if not f.startswith("rotated_")
            and f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        ]
    except Exception:
        files = []

    enabled_set = None
    explicit_set = set()
    priority_map = {}

    try:
        if os.path.exists(EASTER_EGGS_MANIFEST):
            with open(EASTER_EGGS_MANIFEST, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            images = manifest.get("images", {}) if isinstance(manifest, dict) else {}
            if isinstance(images, dict):
                enabled = []
                for name, meta in images.items():
                    if not isinstance(meta, dict):
                        continue
                    if meta.get("enabled", True):
                        enabled.append(name)
                    if meta.get("explicit", False):
                        explicit_set.add(name)
                    prio = max(1, min(10, int(meta.get("priority", 5))))
                    priority_map[name] = prio
                enabled_set = set(enabled)
    except Exception:
        pass

    return files, enabled_set, explicit_set, priority_map


async def get_random_egg() -> Image.Image | None:
    """Pick a random enabled easter egg, respecting explicit filter. Returns PIL Image."""
    if not os.path.exists(EASTER_EGGS_DIR):
        return None

    files, enabled_set, explicit_set, priority_map = _get_candidates()
    candidates = [f for f in files if f in enabled_set] if enabled_set is not None else files

    if not candidates:
        return None

    allow_explicit = await ha_explicit_allowed()
    if not allow_explicit:
        candidates = [f for f in candidates if f not in explicit_set]

    if not candidates:
        return None

    weights = [max(1, priority_map.get(f, 5)) for f in candidates]
    selected = random.choices(candidates, weights=weights, k=1)[0]

    try:
        path = os.path.join(EASTER_EGGS_DIR, selected)
        img = Image.open(path)
        logger.info(f"Selected easter egg: {selected}")
        return img
    except Exception as e:
        logger.warning(f"Failed to load egg {selected}: {e}")
        return None

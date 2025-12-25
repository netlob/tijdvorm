import json
import os
from PIL import Image
from datetime import datetime, timezone
import random

from tijdvorm.config import (
    EASTER_EGGS_DIR, EASTER_EGGS_MANIFEST, EASTER_EGGS_OVERRIDE,
    EASTER_EGGS_SETTINGS, ROTATED_IMAGES_DIR, LIVE_DIR,
    LIVE_PREVIEW_FILENAME, LIVE_STATE_FILENAME
)
from tijdvorm.integrations.home_assistant import ha_explicit_allowed

def load_egg_manifest():
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

def save_egg_manifest(manifest):
    try:
        os.makedirs(EASTER_EGGS_DIR, exist_ok=True)
        tmp_path = EASTER_EGGS_MANIFEST + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)
        os.replace(tmp_path, EASTER_EGGS_MANIFEST)
    except Exception as e:
        print(f"Warning: failed to save manifest.json ({e})")

def get_cached_content_id(filename):
    manifest = load_egg_manifest()
    images = manifest.get("images", {})
    meta = images.get(filename)
    if isinstance(meta, dict):
        cid = meta.get("tv_content_id")
        if isinstance(cid, str) and cid:
            return cid
    return None

def set_cached_content_id(filename, content_id):
    manifest = load_egg_manifest()
    images = manifest.setdefault("images", {})
    meta = images.get(filename)
    if not isinstance(meta, dict):
        meta = {"enabled": True, "explicit": False, "priority": 5, "uploaded_at": None}
    meta["tv_content_id"] = content_id
    images[filename] = meta
    manifest["images"] = images
    save_egg_manifest(manifest)

def preserved_content_ids():
    """All cached easteregg/override content IDs that should never be deleted."""
    manifest = load_egg_manifest()
    images = manifest.get("images", {})
    keep = set()
    if isinstance(images, dict):
        for _, meta in images.items():
            if not isinstance(meta, dict):
                continue
            cid = meta.get("tv_content_id")
            if isinstance(cid, str) and cid:
                keep.add(cid)
    return keep

def get_override_image_path():
    """Returns absolute path to override image if set, otherwise None."""
    try:
        if not os.path.exists(EASTER_EGGS_OVERRIDE):
            return None
        with open(EASTER_EGGS_OVERRIDE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        filename = data.get("filename")
        if not filename or not isinstance(filename, str):
            return None
        filename = os.path.basename(filename)
        candidate = os.path.join(EASTER_EGGS_DIR, filename)
        if not os.path.exists(candidate):
            print(f"Warning: override image not found on disk: {candidate}")
            return None
        return os.path.abspath(candidate)
    except Exception as e:
        print(f"Warning: could not read override.json ({e})")
        return None

def load_easter_egg_settings():
    """Returns settings dict. If missing/invalid, returns defaults."""
    defaults = {"easter_egg_chance_denominator": 10}
    try:
        if not os.path.exists(EASTER_EGGS_SETTINGS):
            return defaults
        with open(EASTER_EGGS_SETTINGS, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return defaults
        denom = data.get("easter_egg_chance_denominator", defaults["easter_egg_chance_denominator"])
        try:
            denom = int(denom)
        except Exception:
            denom = defaults["easter_egg_chance_denominator"]
        if denom < 0:
            denom = 0
        return {"easter_egg_chance_denominator": denom}
    except Exception as e:
        print(f"Warning: could not read settings.json ({e})")
        return defaults

def _get_enabled_easter_egg_candidates():
    """Returns (files_on_disk, enabled_set, explicit_set, priority_map)."""
    files = []
    try:
        files = os.listdir(EASTER_EGGS_DIR)
        files = [
            f
            for f in files
            if f != "manifest.json"
            and f != "override.json"
            and f != "settings.json"
            and not f.startswith("rotated_")
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
                    if not isinstance(name, str) or not isinstance(meta, dict):
                        continue
                    if bool(meta.get("enabled", True)):
                        enabled.append(name)
                    if bool(meta.get("explicit", False)):
                        explicit_set.add(name)
                    # priority 1..10 (higher = more likely)
                    prio = meta.get("priority", 5)
                    try:
                        prio_i = int(prio)
                    except Exception:
                        prio_i = 5
                    if prio_i < 1:
                        prio_i = 1
                    if prio_i > 10:
                        prio_i = 10
                    priority_map[name] = prio_i
                enabled_set = set(enabled)
    except Exception as e:
        print(f"Warning: could not read manifest.json for explicit filtering ({e})")

    return files, enabled_set, explicit_set, priority_map

def get_random_easter_egg_filtered():
    """
    Picks a random enabled image from eastereggs/, filtering explicit images
    if Home Assistant explicit boolean is OFF.
    """
    if not os.path.exists(EASTER_EGGS_DIR):
        return None

    files, enabled_set, explicit_set, priority_map = _get_enabled_easter_egg_candidates()
    if enabled_set is not None:
        candidates = [f for f in files if f in enabled_set]
    else:
        candidates = files

    if not candidates:
        return None

    allow_explicit = ha_explicit_allowed()
    if not allow_explicit:
        candidates = [f for f in candidates if f not in explicit_set]

    if not candidates:
        return None

    weights = [max(1, int(priority_map.get(f, 5))) for f in candidates]
    selected_image = random.choices(candidates, weights=weights, k=1)[0]
    return os.path.join(EASTER_EGGS_DIR, selected_image)

def prepare_rotated_image(source_path):
    """Rotates a static image 180 degrees and saves it to images/rotated/."""
    try:
        img = Image.open(source_path)
        rotated_img = img.rotate(180)
        
        # Ensure directory exists
        os.makedirs(ROTATED_IMAGES_DIR, exist_ok=True)
        
        output_filename = f"rotated_{os.path.basename(source_path)}"
        abs_path = os.path.abspath(os.path.join(ROTATED_IMAGES_DIR, output_filename))
        rotated_img.save(abs_path)
        print(f"Image rotated and saved to: {abs_path}")
        return abs_path
    except Exception as e:
        print(f"Error preparing rotated image: {e}")
        return None

def write_live_preview(uploaded_image_path, meta):
    """
    Writes live/preview.png and live/state.json for the web UI.
    `uploaded_image_path` should be the exact file pushed to the TV (so the preview matches the TV).
    """
    try:
        os.makedirs(LIVE_DIR, exist_ok=True)
        preview_path = os.path.join(LIVE_DIR, LIVE_PREVIEW_FILENAME)
        state_path = os.path.join(LIVE_DIR, LIVE_STATE_FILENAME)

        # Copy preview image (atomic replace)
        tmp_preview = preview_path + ".tmp"
        with open(uploaded_image_path, "rb") as src, open(tmp_preview, "wb") as dst:
            dst.write(src.read())
        os.replace(tmp_preview, preview_path)

        # Write JSON state (atomic replace)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "type": meta.get("type"),
            "filename": meta.get("filename"),
            "url": "/live/preview.png",
        }
        tmp_state = state_path + ".tmp"
        with open(tmp_state, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        os.replace(tmp_state, state_path)
    except Exception as e:
        print(f"Warning: failed to write live preview ({e})")


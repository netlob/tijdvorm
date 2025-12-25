import os
import json
import shutil
import requests
import io
import asyncio
import numpy as np
import face_recognition
import pickle
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timezone
from typing import Any
from concurrent.futures import ThreadPoolExecutor

# Import shared logic from tijdvorm modules
from tijdvorm.config import (
    EASTER_EGGS_DIR, EASTER_EGGS_MANIFEST, EASTER_EGGS_OVERRIDE,
    EASTER_EGGS_SETTINGS, LIVE_DIR, LIVE_STATE_FILENAME, TV_IP,
    DATA_DIR, FACES_DIR, ENCODINGS_FILE
)
from tijdvorm.integrations.samsung import connect_to_tv, update_tv_art
from tijdvorm.integrations.home_assistant import get_sauna_status
from tijdvorm.features.easter_eggs import (
    prepare_rotated_image, preserved_content_ids,
    load_egg_manifest, save_egg_manifest,
)
from tijdvorm.features.sauna import generate_sauna_image
from tijdvorm.features.timeform import generate_timeform_image
from tijdvorm.features.preview import write_live_preview

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Constants from config are used where possible
# FACES_DIR, ENCODINGS_FILE imported from config

MANIFEST_PATH = EASTER_EGGS_MANIFEST
OVERRIDE_PATH = EASTER_EGGS_OVERRIDE
SETTINGS_PATH = EASTER_EGGS_SETTINGS
LIVE_STATE_PATH = os.path.join(LIVE_DIR, LIVE_STATE_FILENAME)

DEFAULT_SETTINGS: dict[str, Any] = {
    # 1 in N chance per cycle. Set to 0 to disable easter eggs.
    "easter_egg_chance_denominator": 10
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    os.makedirs(EASTER_EGGS_DIR, exist_ok=True)
    os.makedirs(LIVE_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)


def _is_allowed_image(filename: str) -> bool:
    lower = filename.lower()
    return lower.endswith((".png", ".jpg", ".jpeg", ".webp"))


def _safe_filename(filename: str) -> str:
    # Keep it simple: drop any path parts, disallow empty
    name = os.path.basename(filename).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return name


def _load_manifest() -> dict[str, Any]:
    _ensure_dirs()
    if not os.path.exists(MANIFEST_PATH):
        return {"version": 1, "images": {}}
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
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


def _save_manifest(manifest: dict[str, Any]) -> None:
    _ensure_dirs()
    tmp_path = MANIFEST_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    os.replace(tmp_path, MANIFEST_PATH)

def _load_settings() -> dict[str, Any]:
    _ensure_dirs()
    if not os.path.exists(SETTINGS_PATH):
        return dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return dict(DEFAULT_SETTINGS)
        merged = dict(DEFAULT_SETTINGS)
        merged.update(data)
        return merged
    except Exception:
        return dict(DEFAULT_SETTINGS)


def _save_settings(settings: dict[str, Any]) -> None:
    _ensure_dirs()
    tmp_path = SETTINGS_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
    os.replace(tmp_path, SETTINGS_PATH)

def _load_override() -> dict[str, Any]:
    _ensure_dirs()
    if not os.path.exists(OVERRIDE_PATH):
        return {"filename": None, "set_at": None}
    try:
        with open(OVERRIDE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"filename": None, "set_at": None}
        filename = data.get("filename")
        if filename is not None and not isinstance(filename, str):
            filename = None
        set_at = data.get("set_at")
        if set_at is not None and not isinstance(set_at, str):
            set_at = None
        return {"filename": filename, "set_at": set_at}
    except Exception:
        return {"filename": None, "set_at": None}


def _save_override(filename: str | None) -> None:
    _ensure_dirs()
    tmp_path = OVERRIDE_PATH + ".tmp"
    payload = {"filename": filename, "set_at": _utc_now_iso() if filename else None}
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    os.replace(tmp_path, OVERRIDE_PATH)


def _sync_manifest_files(manifest: dict[str, Any]) -> dict[str, Any]:
    """Ensure all files in eastereggs exist in manifest; keep manifest entries even if missing."""
    _ensure_dirs()
    images = manifest.get("images", {})
    try:
        files = os.listdir(EASTER_EGGS_DIR)
    except Exception:
        files = []

    for f in files:
        if f == "manifest.json":
            continue
        if f.startswith("rotated_"):
            continue
        if not _is_allowed_image(f):
            continue
        if f not in images:
            images[f] = {"enabled": True, "explicit": False, "priority": 5, "tv_content_id": None, "uploaded_at": None}
        else:
            # Ensure new keys exist for older manifests
            if isinstance(images.get(f), dict):
                images[f].setdefault("explicit", False)
                images[f].setdefault("enabled", True)
                images[f].setdefault("priority", 5)
                images[f].setdefault("tv_content_id", None)

    manifest["images"] = images
    return manifest


app = FastAPI(title="tijdvorm eastereggs")

# Local-network friendly defaults
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_ensure_dirs()
app.mount("/eastereggs", StaticFiles(directory=EASTER_EGGS_DIR), name="eastereggs")
app.mount("/live", StaticFiles(directory=LIVE_DIR), name="live")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/images")
def list_images() -> dict[str, Any]:
    manifest = _sync_manifest_files(_load_manifest())
    _save_manifest(manifest)

    out = []
    for filename, meta in manifest["images"].items():
        prio = 5
        try:
            prio = int(meta.get("priority", 5))
        except Exception:
            prio = 5
        if prio < 1:
            prio = 1
        if prio > 10:
            prio = 10
        out.append(
            {
                "filename": filename,
                "enabled": bool(meta.get("enabled", True)),
                "explicit": bool(meta.get("explicit", False)),
                "priority": prio,
                "uploaded_at": meta.get("uploaded_at"),
                "url": f"/eastereggs/{filename}",
            }
        )
    out.sort(key=lambda x: x["filename"].lower())
    return {"images": out}

@app.get("/api/override")
def get_override() -> dict[str, Any]:
    data = _load_override()
    filename = data.get("filename")
    if filename:
        return {
            "filename": filename,
            "set_at": data.get("set_at"),
            "url": f"/eastereggs/{filename}",
        }
    return {"filename": None, "set_at": None}


@app.post("/api/override")
def set_override(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Body:
      { "filename": "foo.png" } to set override
      { "filename": null } to clear override
    """
    filename = payload.get("filename", None)
    if filename is None:
        _save_override(None)
        return {"ok": True, "filename": None}

    if not isinstance(filename, str):
        raise HTTPException(status_code=400, detail="filename must be a string or null")

    filename = _safe_filename(filename)
    if not _is_allowed_image(filename):
        raise HTTPException(status_code=400, detail="Unsupported file type")

    # Must exist in folder to be selectable
    path = os.path.join(EASTER_EGGS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Image not found on disk")

    _save_override(filename)
    return {"ok": True, "filename": filename, "url": f"/eastereggs/{filename}"}


@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)) -> dict[str, Any]:
    filename = _safe_filename(file.filename or "")
    if not _is_allowed_image(filename):
        raise HTTPException(status_code=400, detail="Unsupported file type")

    _ensure_dirs()
    dst_path = os.path.join(EASTER_EGGS_DIR, filename)
    tmp_path = dst_path + ".uploading"

    try:
        with open(tmp_path, "wb") as f:
            await file.seek(0)
            shutil.copyfileobj(file.file, f)
        os.replace(tmp_path, dst_path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass

    manifest = _load_manifest()
    images = manifest.setdefault("images", {})
    images[filename] = {"enabled": True, "explicit": False, "priority": 5, "tv_content_id": None, "uploaded_at": _utc_now_iso()}
    _save_manifest(manifest)

    return {"ok": True, "filename": filename}


@app.post("/api/images/{filename}/enabled")
def set_enabled(filename: str, payload: dict[str, Any]) -> dict[str, Any]:
    filename = _safe_filename(filename)
    enabled = bool(payload.get("enabled"))

    manifest = _sync_manifest_files(_load_manifest())
    images = manifest.setdefault("images", {})

    if filename not in images:
        raise HTTPException(status_code=404, detail="Image not found")

    images[filename]["enabled"] = enabled
    _save_manifest(manifest)
    return {"ok": True, "filename": filename, "enabled": enabled}

@app.post("/api/images/{filename}/explicit")
def set_explicit(filename: str, payload: dict[str, Any]) -> dict[str, Any]:
    filename = _safe_filename(filename)
    explicit = bool(payload.get("explicit"))

    manifest = _sync_manifest_files(_load_manifest())
    images = manifest.setdefault("images", {})

    if filename not in images:
        raise HTTPException(status_code=404, detail="Image not found")

    if not isinstance(images[filename], dict):
        images[filename] = {"enabled": True, "explicit": explicit, "priority": 5, "tv_content_id": None, "uploaded_at": None}
    else:
        images[filename]["explicit"] = explicit

    _save_manifest(manifest)
    return {"ok": True, "filename": filename, "explicit": explicit}


@app.post("/api/images/{filename}/priority")
def set_priority(filename: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Body:
      { "priority": 1..10 }
    Higher = more likely to show up when it's easter-egg time.
    """
    filename = _safe_filename(filename)
    prio = payload.get("priority")
    if prio is None:
        raise HTTPException(status_code=400, detail="Missing priority")
    try:
        prio_i = int(prio)
    except Exception as e:
        raise HTTPException(status_code=400, detail="priority must be an integer") from e
    if prio_i < 1:
        prio_i = 1
    if prio_i > 10:
        prio_i = 10

    manifest = _sync_manifest_files(_load_manifest())
    images = manifest.setdefault("images", {})
    if filename not in images:
        raise HTTPException(status_code=404, detail="Image not found")

    if not isinstance(images[filename], dict):
        images[filename] = {"enabled": True, "explicit": False, "priority": prio_i, "uploaded_at": None}
    else:
        images[filename]["priority"] = prio_i

    _save_manifest(manifest)
    return {"ok": True, "filename": filename, "priority": prio_i}


def _load_live_state() -> dict[str, Any]:
    _ensure_dirs()
    if not os.path.exists(LIVE_STATE_PATH):
        return {"updated_at": None, "type": None, "filename": None, "url": None}
    try:
        with open(LIVE_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"updated_at": None, "type": None, "filename": None, "url": None}
        return data
    except Exception:
        return {"updated_at": None, "type": None, "filename": None, "url": None}


@app.get("/api/live-preview")
def live_preview() -> dict[str, Any]:
    """
    Returns metadata + URL for the most recently pushed image.
    The image itself is served under /live (StaticFiles).
    """
    data = _load_live_state()
    # Normalize: ensure url is present only if file exists
    url = data.get("url")
    if isinstance(url, str) and url.startswith("/live/"):
        path = os.path.join(LIVE_DIR, os.path.basename(url))
        if not os.path.exists(path):
            url = None
    else:
        url = None

    return {
        "updated_at": data.get("updated_at"),
        "type": data.get("type"),
        "filename": data.get("filename"),
        "url": url,
    }

@app.delete("/api/images/{filename}")
def delete_image(filename: str) -> dict[str, Any]:
    filename = _safe_filename(filename)
    path = os.path.join(EASTER_EGGS_DIR, filename)

    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {e}") from e

    manifest = _load_manifest()
    images = manifest.get("images", {})
    if filename in images:
        images.pop(filename, None)
        manifest["images"] = images
        _save_manifest(manifest)

    return {"ok": True, "filename": filename}


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    settings = _load_settings()
    # Normalize
    denom = settings.get("easter_egg_chance_denominator", DEFAULT_SETTINGS["easter_egg_chance_denominator"])
    try:
        denom = int(denom)
    except Exception:
        denom = DEFAULT_SETTINGS["easter_egg_chance_denominator"]
    if denom < 0:
        denom = 0
    return {"easter_egg_chance_denominator": denom}


@app.post("/api/settings")
def set_settings(payload: dict[str, Any]) -> dict[str, Any]:
    denom = payload.get("easter_egg_chance_denominator")
    if denom is None:
        raise HTTPException(status_code=400, detail="Missing easter_egg_chance_denominator")
    try:
        denom_i = int(denom)
    except Exception as e:
        raise HTTPException(status_code=400, detail="easter_egg_chance_denominator must be an integer") from e
    if denom_i < 0:
        denom_i = 0

    settings = dict(DEFAULT_SETTINGS)
    settings["easter_egg_chance_denominator"] = denom_i
    _save_settings(settings)
    return {"ok": True, "easter_egg_chance_denominator": denom_i}


# --- Face Recognition State ---
KNOWN_FACE_ENCODINGS = []
KNOWN_FACE_NAMES = []
DOORBELL_ACTIVE = False
TV_BUSY = False

def load_known_faces():
    """Loads face encodings from pickle file if exists, else warns."""
    global KNOWN_FACE_ENCODINGS, KNOWN_FACE_NAMES
    
    print("[Face Rec] Loading known faces...", flush=True)
    
    if os.path.exists(ENCODINGS_FILE):
        try:
            with open(ENCODINGS_FILE, "rb") as f:
                data = pickle.load(f)
            KNOWN_FACE_ENCODINGS = data["encodings"]
            KNOWN_FACE_NAMES = data["names"]
            print(f"[Face Rec] Loaded {len(KNOWN_FACE_NAMES)} faces from cache.", flush=True)
            return
        except Exception as e:
            print(f"[Face Rec] Failed to load cache: {e}", flush=True)

    print("[Face Rec] No cache found or load failed. Please run 'python scripts/train_faces.py'.", flush=True)
    print("[Face Rec] Starting with empty face database.", flush=True)

# Load faces on startup
load_known_faces()


async def doorbell_recognition_loop():
    """
    Background loop that runs while DOORBELL_ACTIVE is True.
    Fetches snapshot -> Detects Faces -> Updates TV if recognized.
    """
    global DOORBELL_ACTIVE, TV_BUSY
    
    snapshot_url = "http://nvr.netlob/cgi-bin/api.cgi?cmd=Snap&channel=0&rs=wuuPhkmUCeI9WG7C&user=api&password=peepeepoopoo"
    filename = "doorbell.jpg"
    
    print("[Doorbell Loop] Started.", flush=True)
    
    while DOORBELL_ACTIVE:
        if TV_BUSY:
            await asyncio.sleep(1)
            continue
            
        try:
            # 1. Fetch
            try:
                resp = requests.get(snapshot_url, timeout=5)
                resp.raise_for_status()
            except Exception as e:
                print(f"[Doorbell Loop] Fetch failed: {e}", flush=True)
                await asyncio.sleep(1)
                continue

            # 2. Process (Resize/Crop first for consistency with main handler)
            # We need to process it to the target dimensions BEFORE detection
            # so the boxes match what is shown on TV.
            img = Image.open(io.BytesIO(resp.content))
            TARGET_WIDTH = 1080
            TARGET_HEIGHT = 1920
            
            # Resize/Crop logic (same as _handle_doorbell)
            original_width, original_height = img.size
            ratio = TARGET_HEIGHT / original_height
            new_width = int(original_width * ratio)
            new_height = TARGET_HEIGHT
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # 2. Crop to 1080 width, aligned center
            left_offset = (new_width - TARGET_WIDTH) // 2
            img_cropped = img_resized.crop((left_offset, 0, left_offset + TARGET_WIDTH, TARGET_HEIGHT))
            
            # 3. Detect Faces
            # Convert PIL to numpy array (RGB)
            img_np = np.array(img_cropped)
            
            # Optimization: Resize for detection (1/4 size)
            small_frame = np.ascontiguousarray(img_np[::4, ::4])
            
            # Find faces
            face_locations = face_recognition.face_locations(small_frame)
            face_encodings = face_recognition.face_encodings(small_frame, face_locations)
            
            recognized_names = []
            
            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(KNOWN_FACE_ENCODINGS, face_encoding, tolerance=0.6)
                name = "Unknown"
                
                if True in matches:
                    first_match_index = matches.index(True)
                    name = KNOWN_FACE_NAMES[first_match_index]
                    recognized_names.append(name)

            # 4. If recognized faces found, update TV
            if recognized_names:
                print(f"[Doorbell Loop] Recognized: {recognized_names}", flush=True)
                
                # Draw boxes/names on full size image
                draw = ImageDraw.Draw(img_cropped)
                font_size = 40
                try:
                    # Try loading a font
                    font = ImageFont.truetype(os.path.join("assets", "fonts", "Inter-Regular.otf"), font_size)
                except:
                    font = ImageFont.load_default()

                for (top, right, bottom, left), name in zip(face_locations, recognized_names): # Note: iterating detected faces
                    # Scale back up by 4
                    top *= 4
                    right *= 4
                    bottom *= 4
                    left *= 4
                    
                    # Draw box
                    draw.rectangle(((left, top), (right, bottom)), outline=(0, 255, 0), width=5)
                    
                    # Draw text background
                    text_bbox = draw.textbbox((left, bottom), name, font=font)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_height = text_bbox[3] - text_bbox[1]
                    draw.rectangle(((left, bottom), (left + text_width + 10, bottom + text_height + 10)), fill=(0, 255, 0), outline=(0, 255, 0))
                    draw.text((left + 5, bottom + 5), name, fill=(255, 255, 255, 255), font=font)

                # Save to disk
                _ensure_dirs()
                file_path = os.path.join(EASTER_EGGS_DIR, filename)
                img_cropped.save(file_path, quality=95)
                
                # Push to TV
                if not TV_BUSY:
                    TV_BUSY = True
                    try:
                        print(f"[Doorbell Loop] Updating TV with recognized faces...", flush=True)
                        rotated_path = prepare_rotated_image(file_path)
                        if rotated_path:
                            # Run synchronous TV update in thread
                            loop = asyncio.get_running_loop()
                            await loop.run_in_executor(None, _push_to_tv_sync, rotated_path)
                    except Exception as e:
                        print(f"[Doorbell Loop] Update failed: {e}", flush=True)
                    finally:
                        TV_BUSY = False
            
            else:
                 # No recognized faces, do nothing (or maybe update anyway if movement? User said "if someone is recognized update")
                 pass

        except Exception as e:
            print(f"[Doorbell Loop] Error: {e}", flush=True)
            
        await asyncio.sleep(1) # Fetch every second

    print("[Doorbell Loop] Stopped.", flush=True)

def _push_to_tv_sync(image_path):
    """Helper to run TV update synchronously."""
    tv = connect_to_tv(TV_IP)
    if tv:
        preserve = preserved_content_ids()
        update_tv_art(tv, image_path, preserve_ids=preserve)


def _handle_doorbell(data: dict[str, Any], background_tasks: BackgroundTasks) -> dict[str, Any]:
    global DOORBELL_ACTIVE
    
    # Enable Loop if not already running
    if not DOORBELL_ACTIVE:
        DOORBELL_ACTIVE = True
        background_tasks.add_task(doorbell_recognition_loop)
    
    snapshot_url = "http://nvr.netlob/cgi-bin/api.cgi?cmd=Snap&channel=0&rs=wuuPhkmUCeI9WG7C&user=api&password=peepeepoopoo"
    filename = "doorbell.jpg"

    
    # 1. Fetch Snapshot
    try:
        print(f"[Doorbell] Fetching snapshot from {snapshot_url}...", flush=True)
        resp = requests.get(snapshot_url, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"[Doorbell] Failed to fetch snapshot: {e}", flush=True)
        raise HTTPException(status_code=502, detail="Failed to fetch doorbell snapshot")

    # 2. Process and Save to disk
    _ensure_dirs()
    file_path = os.path.join(EASTER_EGGS_DIR, filename)
    try:
        # Load image from bytes
        img = Image.open(io.BytesIO(resp.content))
        
        # Target Dimensions
        TARGET_WIDTH = 1080
        TARGET_HEIGHT = 1920
        
        # 1. Resize to fill height
        # Calculate aspect ratio
        original_width, original_height = img.size
        # ratio to fill height
        ratio = TARGET_HEIGHT / original_height
        new_width = int(original_width * ratio)
        new_height = TARGET_HEIGHT # should be 1920
        
        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # 2. Crop to 1080 width, aligned center
        # Calculate left offset to center the crop
        left_offset = (new_width - TARGET_WIDTH) // 2
        img_cropped = img_resized.crop((left_offset, 0, left_offset + TARGET_WIDTH, TARGET_HEIGHT))
        
        # Save processed image
        img_cropped.save(file_path, quality=95)
        print(f"[Doorbell] Processed image saved to {file_path} ({TARGET_WIDTH}x{TARGET_HEIGHT})", flush=True)

    except Exception as e:
        print(f"[Doorbell] Failed to process/save snapshot: {e}", flush=True)
        raise HTTPException(status_code=500, detail="Failed to process/save snapshot")

    # 3. Set Override (so main loop respects it if it wakes up)
    _save_override(filename)
    
    # 4. Immediate TV Update (First Frame)
    if not TV_BUSY:
        background_tasks.add_task(_initial_push, file_path)
    
    return {"ok": True, "status": "override_set_pending_update"}

async def _initial_push(file_path: str):
    """Push the initial frame in background to not block the request, but immediately."""
    global TV_BUSY
    if TV_BUSY: return
    TV_BUSY = True
    try:
        print("[Doorbell] Rotating initial image...", flush=True)
        rotated_path = prepare_rotated_image(file_path)
        if rotated_path:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _push_to_tv_sync, rotated_path)
    except Exception as e:
         print(f"[Doorbell] Initial push failed: {e}", flush=True)
    finally:
         TV_BUSY = False


async def _handle_doorbell_off() -> dict[str, Any]:
    global DOORBELL_ACTIVE, TV_BUSY
    
    # Stop the loop
    DOORBELL_ACTIVE = False
    
    # 1. Clear Override
    _save_override(None)
    
    # 2. Restore default art immediately
    # Wait if TV is busy (e.g. upload in progress)
    retries = 0
    while TV_BUSY and retries < 15:
            await asyncio.sleep(1)
            retries += 1

    try:
        TV_BUSY = True
        print("[Doorbell] Doorbell OFF received. Restoring default art...", flush=True)
        
        # Check Sauna Logic (replicate main_loop behavior)
        sauna_status = get_sauna_status()
        image_path = None
        live_meta = {}

        if sauna_status and sauna_status.get('is_on'):
                print("[Doorbell] Sauna is ON. Generating sauna image...", flush=True)
                image_path = await generate_sauna_image(sauna_status)
                live_meta = {"type": "sauna", "filename": os.path.basename(image_path) if image_path else None}
        else:
                print("[Doorbell] Generating Timeform image...", flush=True)
                image_path = await generate_timeform_image()
                live_meta = {"type": "timeform", "filename": os.path.basename(image_path) if image_path else None}

        if image_path:
                print(f"[Doorbell] Connecting to TV at {TV_IP}...", flush=True)
                # Run sync connection in thread
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, _push_to_tv_sync, image_path)
                
                # Update live preview
                write_live_preview(image_path, live_meta)
                return {"ok": True, "status": "restored"}
        else:
                print("[Doorbell] Failed to generate restore image.", flush=True)

    except Exception as e:
        print(f"[Doorbell] Error restoring TV: {e}", flush=True)
    finally:
        TV_BUSY = False

    return {"ok": True, "status": "override_cleared_pending_update"}


@app.post("/api/ha")
async def ha_webhook(payload: dict[str, Any], background_tasks: BackgroundTasks) -> dict[str, Any]:
    """
    Unified endpoint for Home Assistant automations.
    Payload format:
      {
        "action": "doorbell" | "doorbell_on" | "doorbell_off",
        "data": { ... }
      }
    """
    action = payload.get("action")
    data = payload.get("data", {})
    if not isinstance(data, dict):
        data = {}

    if action == "doorbell" or action == "doorbell_on":
        return _handle_doorbell(data, background_tasks)
    elif action == "doorbell_off":
        return await _handle_doorbell_off()
    
    raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("BACKEND_HOST", "0.0.0.0")
    port = int(os.environ.get("BACKEND_PORT", "8000"))
    print(f"[tijdvorm] starting API on http://{host}:{port}", flush=True)
    try:
        # Run using the in-memory app object (avoids any import-string weirdness)
        uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)
    except OSError as e:
        # Common: address already in use
        print(f"[tijdvorm] failed to start server: {e}", flush=True)
        print(f"[tijdvorm] is something already using port {port}? try: lsof -i :{port}", flush=True)
        raise

import os
import sys

# Add project root to sys.path to allow imports from backend.*
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
import shutil
import requests
import io
import time
import asyncio
import subprocess
import signal
import numpy as np
# import face_recognition  <-- Moved to lazy import to avoid startup crashes if models are missing
# Patch for Python 3.13+ missing pkg_resources
try:
    from backend.utils import face_rec_patch
except ImportError:
    pass

import pickle
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timezone
from typing import Any, Optional, Union
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Request, Response
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Import shared logic from backend modules
from backend.config import (
    EASTER_EGGS_DIR, EASTER_EGGS_MANIFEST, EASTER_EGGS_OVERRIDE,
    EASTER_EGGS_SETTINGS, LIVE_DIR, LIVE_STATE_PATH, TV_IP,
    DATA_DIR, FACES_DIR, ENCODINGS_FILE, USE_PYTHON_DOORBELL_PUSH, ASSETS_DIR,
    HDMI_SOURCE_KEY, BACKEND_PUBLIC_URL
)
from backend.integrations.samsung import connect_to_tv, update_tv_art, switch_to_hdmi, set_art_mode_active
from backend.integrations.home_assistant import get_sauna_status
from backend.features.easter_eggs import (
    prepare_rotated_image, preserved_content_ids,
    load_egg_manifest, save_egg_manifest,
)
from backend.features.sauna import generate_sauna_image
from backend.features.timeform import generate_timeform_image
from backend.features.preview import write_live_preview
from backend.integrations.airplay import play_url_on_tv, get_local_ip, stop_airplay
from backend.integrations.dlna import play_url_via_dlna, stop_dlna
from backend.features.hdmi_display import start_hdmi_display, stop_hdmi_display
import tempfile

# Constants from config are used where possible
# FACES_DIR, ENCODINGS_FILE imported from config

MANIFEST_PATH = EASTER_EGGS_MANIFEST
OVERRIDE_PATH = EASTER_EGGS_OVERRIDE
SETTINGS_PATH = EASTER_EGGS_SETTINGS

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


def _save_override(filename: Optional[str]) -> None:
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
app.mount("/hls", StaticFiles(directory="data/hls"), name="hls")

@app.on_event("startup")
async def _startup_ffmpeg():
    # Start persistent ffmpeg transcoder so HLS segments stay hot
    # start_transcoding() # Disabled to save CPU
    pass


@app.on_event("shutdown")
async def _shutdown_ffmpeg():
    # stop_transcoding()
    pass

# Global variable to track the ffmpeg process (persistent, hot pipeline)
FFMPEG_PROCESS = None

def _spawn_ffmpeg_hls():
    """
    Launch persistent ffmpeg to keep HLS segments warm.
    Returns Popen instance.
    """
    # Ensure HLS directory exists
    os.makedirs("data/hls", exist_ok=True)

    # Clean up old segments
    for f in os.listdir("data/hls"):
        try:
            os.remove(os.path.join("data/hls", f))
        except Exception:
            pass

    rtsp_url = "rtsp://api:peepeepoopoo@nvr.netlob:554/h264Preview_01_main"
    # Optimized filter: scale first (hardware/faster), then crop. 
    # Also using zerolatency tuning is good, but let's ensure preset is ultrafast.
    # We want 1080x1920 output.
    filter_complex = "crop=in_w:in_h-60:0:60,scale=-1:1920,crop=1080:1920:(in_w-1080)/2:0,transpose=2,transpose=2"

    cmd = [
        "ffmpeg",
        "-y",
        "-rtsp_transport", "tcp",
        "-i", rtsp_url,
        "-vf", filter_complex,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-b:v", "3000k",
        "-maxrate", "3000k",
        "-bufsize", "6000k", # Increased buffer for stability
        "-g", "10",             # keyframe every 0.5s (20fps source)
        "-sc_threshold", "0",
        "-f", "hls",
        "-hls_time", "0.5",     # 0.5s segments for low startup
        "-hls_list_size", "3",  # keep only 3 segments
        "-hls_flags", "delete_segments+append_list+omit_endlist",
        "-hls_segment_filename", "data/hls/segment_%03d.ts",
        "data/hls/playlist.m3u8"
    ]

    print(f"[Transcode] Starting ffmpeg (persistent): {' '.join(cmd)}")
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_transcoding():
    global FFMPEG_PROCESS
    if FFMPEG_PROCESS and FFMPEG_PROCESS.poll() is None:
        return  # Already running
    FFMPEG_PROCESS = _spawn_ffmpeg_hls()


def stop_transcoding():
    global FFMPEG_PROCESS
    if FFMPEG_PROCESS and FFMPEG_PROCESS.poll() is None:
        print("[Transcode] Stopping ffmpeg...")
        FFMPEG_PROCESS.terminate()
        try:
            FFMPEG_PROCESS.wait(timeout=5)
        except subprocess.TimeoutExpired:
            FFMPEG_PROCESS.kill()
    FFMPEG_PROCESS = None
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

@app.get("/eastereggs/{filename}")
def get_easteregg(filename: str) -> dict[str, Any]:
    path = os.path.join(EASTER_EGGS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Image not found on disk")
    return FileResponse(path, media_type=get_media_type(path))

def get_media_type(path: str) -> str:
    if path.endswith(".png"):
        return "image/png"
    if path.endswith(".jpg"):
        return "image/jpeg"
    if path.endswith(".jpeg"):
        return "image/jpeg"
    if path.endswith(".webp"):
        return "image/webp"
    return "application/octet-stream"

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
    
    # Lazy import to prevent server crash if face_recognition is broken
    try:
        global face_recognition
        import face_recognition
    except (ImportError, SystemExit, Exception) as e:
        print(f"[Face Rec] Failed to import face_recognition: {e}. Feature disabled.", flush=True)
        return

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

# Load faces on startup (lazily if possible, but here we just call it safe now)
load_known_faces()

def fetch_and_process_doorbell_snapshot():
    """
    Fetches snapshot, processes it (resize/crop/face rec/draw), saves to disk,
    and returns PIL Image.
    """
    snapshot_url = "http://nvr.netlob/cgi-bin/api.cgi?cmd=Snap&channel=0&rs=wuuPhkmUCeI9WG7C&user=api&password=peepeepoopoo"
    filename = "doorbell.jpg"
    
    # 1. Fetch
    try:
        resp = requests.get(snapshot_url, timeout=5)
        resp.raise_for_status()
    except Exception as e:
        print(f"[Doorbell Proxy] Fetch failed: {e}")
        return None

    # 2. Process
    try:
        img = Image.open(io.BytesIO(resp.content))
        TARGET_WIDTH = 1080
        TARGET_HEIGHT = 1920
        
        # 1. Crop Top 60px
        # Source is 1920 x 2560 (or similar)
        # img.crop((left, top, right, bottom))
        w, h = img.size
        # Cut 60 from top
        img = img.crop((0, 60, w, h))
        w, h = img.size # 1920 x 2500
        
        # 2. Resize so height becomes 1920
        # h -> TARGET_HEIGHT
        ratio = TARGET_HEIGHT / h
        new_width = int(w * ratio)
        # new_height will be exactly TARGET_HEIGHT (1920)
        img_resized = img.resize((new_width, TARGET_HEIGHT), Image.Resampling.LANCZOS)
        
        # 3. Crop to 1080 width, aligned LEFT
        # We want (0, 0, 1080, 1920)
        img_cropped = img_resized.crop((0, 0, TARGET_WIDTH, TARGET_HEIGHT))
        
        # Detect Faces
        img_np = np.array(img_cropped)
        small_frame = np.ascontiguousarray(img_np[::4, ::4])
        
        try:
            # Ensure face_recognition is available
            if 'face_recognition' not in globals():
                import face_recognition
                
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
        except (ImportError, SystemExit, Exception) as e:
            print(f"[Face Rec] Detection failed or library missing: {e}")
            face_locations = []
            recognized_names = []

        # Draw
        draw = ImageDraw.Draw(img_cropped)
        font_size = 40
        try:
            font = ImageFont.truetype(os.path.join(ASSETS_DIR, "fonts", "Inter-Regular.otf"), font_size)
        except:
            font = ImageFont.load_default()

        for (top, right, bottom, left), name in zip(face_locations, recognized_names):
            top *= 4; right *= 4; bottom *= 4; left *= 4
            draw.rectangle(((left, top), (right, bottom)), outline=(0, 255, 0), width=5)
            text_bbox = draw.textbbox((left, bottom), name, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            draw.rectangle(((left, bottom), (left + text_width + 10, bottom + text_height + 10)), fill=(0, 255, 0), outline=(0, 255, 0))
            draw.text((left + 5, bottom + 5), name, fill=(255, 255, 255, 255), font=font)

        # Save to disk (cache/update state)
        _ensure_dirs()
        file_path = os.path.join(EASTER_EGGS_DIR, filename)
        img_cropped.save(file_path, quality=95)
        
        return img_cropped
        
    except Exception as e:
        print(f"[Doorbell Proxy] Processing failed: {e}")
        return None


async def doorbell_recognition_loop():
    """
    Background loop that runs while DOORBELL_ACTIVE is True.
    Fetches snapshot -> Detects Faces -> Updates TV if recognized.
    """
    global DOORBELL_ACTIVE, TV_BUSY
    
    print("[Doorbell Loop] Started.", flush=True)
    
    while DOORBELL_ACTIVE:
        if TV_BUSY and USE_PYTHON_DOORBELL_PUSH: 
            await asyncio.sleep(1)
            continue
            
        try:
            # Use shared fetch/process logic
            img = fetch_and_process_doorbell_snapshot()
            
            # If enabled, Push to TV (logic moved here from old loop)
            if img and USE_PYTHON_DOORBELL_PUSH:
                # We need to know if faces were found to decide to push?
                # The shared function doesn't return that metadata easily.
                # For now, let's assume if we are using the proxy, we don't push via python loop.
                # If the user wants python push, they probably aren't using the proxy.
                pass 
                
                # If we really need to support python push again, we'd need to check for changes/faces.
                # But user explicitly asked for HA render variant where we DON'T push.
            
        except Exception as e:
            print(f"[Doorbell Loop] Error: {e}", flush=True)
            
        await asyncio.sleep(1) # Fetch every second

    print("[Doorbell Loop] Stopped.", flush=True)

async def push_to_tv_async(image_path):
    """Helper to run TV update asynchronously."""
    tv = await connect_to_tv(TV_IP)
    if tv:
        try:
            preserve = preserved_content_ids()
            await update_tv_art(tv, image_path, preserve_ids=preserve)
        finally:
            # Ensure we close the connection in server context as it's a one-off
            await tv.close()


def _handle_doorbell(data: dict[str, Any], background_tasks: BackgroundTasks) -> dict[str, Any]:
    global DOORBELL_ACTIVE
    
    # Enable Loop if not already running
    if not DOORBELL_ACTIVE:
        DOORBELL_ACTIVE = True
        # background_tasks.add_task(doorbell_recognition_loop)
    
    # Trigger one immediate fetch/process so the file is ready
    # fetch_and_process_doorbell_snapshot()
    
    # filename = "doorbell.jpg"
    # _save_override(filename)
    
    # Start Transcoding - DISABLED
    # start_transcoding()
    
    # DLNA Stream - DISABLED
    # local_ip = get_local_ip()
    # stream_url = f"http://{local_ip}:8000/hls/playlist.m3u8"
    # print(f"[Doorbell] Attempting DLNA stream to TV: {stream_url}", flush=True)
    
    # 4. Immediate TV Update (First Frame) - ONLY if enabled
    if USE_PYTHON_DOORBELL_PUSH:
        filename = "doorbell.jpg" # Fix: filename wasn't defined in this scope if unused
        file_path = os.path.join(EASTER_EGGS_DIR, filename)
        if not TV_BUSY:
            background_tasks.add_task(_initial_push, file_path)
    
    # 5. HDMI Switch & Display (Pi)
    # Start display on remote HDMI (Pi)
    print(f"[Doorbell] Starting HDMI display stream...", flush=True)
    # Use public URL so Pi can reach us
    # Pass 'ready_callback' param so the page calls us back when image loads
    ready_callback = f"{BACKEND_PUBLIC_URL}/api/doorbell/ready"
    start_hdmi_display(f"{BACKEND_PUBLIC_URL}/view/doorbell?callback={ready_callback}")
    
    # We DO NOT switch HDMI yet. We wait for the /api/doorbell/ready callback.
    
    return {"ok": True, "status": "doorbell_active"}

@app.post("/api/doorbell/ready")
async def doorbell_stream_ready(background_tasks: BackgroundTasks):
    """Called by the frontend (Pi browser) when the first frame is loaded."""
    global TV_BUSY
    print(f"[Doorbell] Stream ready! Switching TV to HDMI ({HDMI_SOURCE_KEY})...", flush=True)
    background_tasks.add_task(switch_to_hdmi, TV_IP, HDMI_SOURCE_KEY)
    return {"ok": True}

async def _initial_push(file_path: str):
    """Push the initial frame in background to not block the request, but immediately."""
    global TV_BUSY
    if TV_BUSY: return
    TV_BUSY = True
    try:
        print("[Doorbell] Rotating initial image...", flush=True)
        rotated_path = prepare_rotated_image(file_path)
        if rotated_path:
            await push_to_tv_async(rotated_path)
    except Exception as e:
         print(f"[Doorbell] Initial push failed: {e}", flush=True)
    finally:
         TV_BUSY = False


async def _handle_doorbell_off() -> dict[str, Any]:
    global DOORBELL_ACTIVE, TV_BUSY
    
    # Stop the loop
    DOORBELL_ACTIVE = False

    # Stop HDMI Display & Switch back to Art Mode
    print("[Doorbell] Stopping HDMI display and restoring Art Mode...", flush=True)
    stop_hdmi_display()
    await set_art_mode_active(TV_IP, True)
    
    # Stop AirPlay / DLNA
    # await stop_airplay()
    # await asyncio.to_thread(stop_dlna)
    
    # Stop Transcoding
    # stop_transcoding()
    
    # 1. Clear Override
    _save_override(None)
    
    # 2. Restore default art immediately
    
    if USE_PYTHON_DOORBELL_PUSH:
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
                 # Run async connection directly
                 await push_to_tv_async(image_path)
                 
                 # Update live preview
                 write_live_preview(image_path, live_meta)
                 return {"ok": True, "status": "restored"}
            else:
                 print("[Doorbell] Failed to generate restore image.", flush=True)

        except Exception as e:
            print(f"[Doorbell] Error restoring TV: {e}", flush=True)
        finally:
            TV_BUSY = False

    return {"ok": True, "status": "doorbell_off"}

@app.api_route("/api/render/doorbell.jpg", methods=["GET", "HEAD"])
async def render_doorbell(request: Request):
    """
    Serve a processed JPEG with Content-Length (no chunked streaming) for maximum compatibility.
    Supports HEAD.
    """
    # Force .jpg extension in URL for strict DLNA/TV parsers
    img_processed = fetch_and_process_doorbell_snapshot()
    if not img_processed:
        # Fallback to existing file if fetch fails
        filename = "doorbell.jpg"
        file_path = os.path.join(EASTER_EGGS_DIR, filename)
        if os.path.exists(file_path):
            # print("[Doorbell Proxy] Fetch failed, using cached file.") # Reduce noise
            img_processed = Image.open(file_path)
        else:
            raise HTTPException(status_code=502, detail="Failed to fetch snapshot")

    # Rotate 180 for TV
    img_rotated = img_processed.rotate(180)

    # Save to a temp file to ensure Content-Length header
    # Using a deterministic name based on time might help caching, but we use random temp for thread safety
    # Actually, we can reuse a single file path if we lock, but temp is safer.
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp_path = tmp.name
    tmp.close()
    img_rotated.save(tmp_path, "JPEG", quality=90)

    # Prepare headers
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
        "Content-Type": "image/jpeg",
        "Access-Control-Allow-Origin": "*", # Ensure CORS for TV browser
    }

    if request.method == "HEAD":
        try:
            size = os.path.getsize(tmp_path)
            headers["Content-Length"] = str(size)
        except Exception:
            pass
        os.remove(tmp_path)
        return Response(status_code=200, media_type="image/jpeg", headers=headers)

    tasks = BackgroundTasks()
    tasks.add_task(os.remove, tmp_path)
    return FileResponse(
        tmp_path,
        media_type="image/jpeg",
        filename="doorbell.jpg",
        headers=headers,
        background=tasks,
    )

def get_camera_frame_generator():
    """
    Generator that endlessly yields multipart frames for MJPEG streaming.
    Loops as fast as possible to keep stream live.
    """
    boundary = "frame"
    while True:
        # Use specialized fetch that skips face recognition for speed
        img_processed = fetch_fast_snapshot()
        
        if img_processed:
            try:
                # Rotate
                # img_rotated = img_processed.rotate(180)
                img_rotated = img_processed
                img_io = io.BytesIO()
                # Reduce JPEG quality slightly for speed (85 vs 90)
                img_rotated.save(img_io, 'JPEG', quality=85)
                frame_bytes = img_io.getvalue()
                
                # Yield frame in MJPEG format
                yield (
                    f"--{boundary}\r\n".encode() +
                    b"Content-Type: image/jpeg\r\n\r\n" +
                    frame_bytes +
                    b"\r\n"
                )
            except Exception as e:
                print(f"[Stream] Error processing frame: {e}")
        
        # Max 10 FPS (0.1s sleep) - much smoother than 1 FPS
        time.sleep(0.1)

def fetch_fast_snapshot():
    """
    Faster snapshot fetch that skips face recognition and drawing.
    Just fetch -> crop/resize -> return.
    """
    snapshot_url = "http://nvr.netlob/cgi-bin/api.cgi?cmd=Snap&channel=0&rs=wuuPhkmUCeI9WG7C&user=api&password=peepeepoopoo"
    try:
        resp = requests.get(snapshot_url, timeout=2)
        resp.raise_for_status()
        
        img = Image.open(io.BytesIO(resp.content))
        TARGET_WIDTH = 1080
        TARGET_HEIGHT = 1920
        
        # 1. Crop Top 60px
        w, h = img.size
        img = img.crop((0, 0, w, h-60))
        w, h = img.size
        
        # 2. Resize
        ratio = TARGET_HEIGHT / h
        new_width = int(w * ratio)
        img_resized = img.resize((new_width, TARGET_HEIGHT), Image.Resampling.NEAREST) # Nearest neighbor is faster
        
        # 3. Crop Center/Left
        img_cropped = img_resized.crop((0, 0, TARGET_WIDTH, TARGET_HEIGHT))
        
        return img_cropped
    except Exception as e:
        # print(f"[Fast Stream] Error: {e}")
        return None

@app.get("/view/doorbell", response_class=HTMLResponse)
async def view_doorbell(request: Request):
    callback = request.query_params.get("callback")
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Doorbell View</title>
        <style>
            body {{ margin: 0; padding: 0; background: black; overflow: hidden; height: 100vh; display: flex; justify-content: center; align-items: center; }}
            img {{ width: 100%; height: 100%; object-fit: cover; opacity: 0; transition: opacity 0.2s; }}
            img.loaded {{ opacity: 1; }}
        </style>
    </head>
    <body>
        <img id="stream" src="/api/stream/doorbell" alt="Doorbell Stream" onerror="this.src='/api/stream/doorbell?t='+new Date().getTime()">
        <script>
            const img = document.getElementById('stream');
            const callbackUrl = "{callback}";
            
            // When first frame loads
            img.onload = function() {{
                if (!img.classList.contains('loaded')) {{
                    img.classList.add('loaded');
                    if (callbackUrl && callbackUrl !== "None") {{
                        console.log("Stream loaded, calling callback:", callbackUrl);
                        fetch(callbackUrl, {{ method: 'POST' }})
                            .catch(e => console.error("Callback failed:", e));
                    }}
                }}
            }};
        </script>
    </body>
    </html>
    """

@app.get("/api/stream/doorbell")
async def stream_doorbell():
    """
    MJPEG Stream for live doorbell view on TV.
    Content-Type: multipart/x-mixed-replace; boundary=frame
    """
    return StreamingResponse(
        get_camera_frame_generator(), 
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

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


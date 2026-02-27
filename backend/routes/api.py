"""Easter egg management API — CRUD, settings, override, live preview."""

import json
import logging
import os
import shutil

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.config import (
    DATA_DIR, EASTER_EGGS_DIR, EASTER_EGGS_MANIFEST,
    EASTER_EGGS_OVERRIDE, EASTER_EGGS_SETTINGS,
    LIVE_DIR, LIVE_STATE_PATH,
)

logger = logging.getLogger("tijdvorm.api")

router = APIRouter(prefix="/api")

DEFAULT_SETTINGS: dict[str, Any] = {
    "easter_egg_chance_denominator": 10,
}


# ── Helpers ──────────────────────────────────────────────────────────

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs():
    os.makedirs(EASTER_EGGS_DIR, exist_ok=True)
    os.makedirs(LIVE_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)


def _is_allowed_image(filename: str) -> bool:
    return filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))


def _safe_filename(filename: str) -> str:
    name = os.path.basename(filename).strip()
    if not name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return name


def _media_type(path: str) -> str:
    if path.endswith(".png"):
        return "image/png"
    if path.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if path.endswith(".webp"):
        return "image/webp"
    return "application/octet-stream"


def _load_manifest() -> dict[str, Any]:
    _ensure_dirs()
    if not os.path.exists(EASTER_EGGS_MANIFEST):
        return {"version": 1, "images": {}}
    try:
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


def _save_manifest(manifest: dict[str, Any]):
    _ensure_dirs()
    tmp = EASTER_EGGS_MANIFEST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    os.replace(tmp, EASTER_EGGS_MANIFEST)


def _sync_manifest_files(manifest: dict[str, Any]) -> dict[str, Any]:
    """Ensure all files on disk appear in manifest."""
    _ensure_dirs()
    images = manifest.get("images", {})
    try:
        files = os.listdir(EASTER_EGGS_DIR)
    except Exception:
        files = []

    for f in files:
        if f.startswith("rotated_") or not _is_allowed_image(f):
            continue
        if f not in images:
            images[f] = {
                "enabled": True, "explicit": False,
                "priority": 5, "uploaded_at": None,
            }
        elif isinstance(images[f], dict):
            images[f].setdefault("explicit", False)
            images[f].setdefault("enabled", True)
            images[f].setdefault("priority", 5)

    manifest["images"] = images
    return manifest


def _load_settings() -> dict[str, Any]:
    _ensure_dirs()
    if not os.path.exists(EASTER_EGGS_SETTINGS):
        return dict(DEFAULT_SETTINGS)
    try:
        with open(EASTER_EGGS_SETTINGS, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return dict(DEFAULT_SETTINGS)
        merged = dict(DEFAULT_SETTINGS)
        merged.update(data)
        return merged
    except Exception:
        return dict(DEFAULT_SETTINGS)


def _save_settings(settings: dict[str, Any]):
    _ensure_dirs()
    tmp = EASTER_EGGS_SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, sort_keys=True)
    os.replace(tmp, EASTER_EGGS_SETTINGS)


def _load_override() -> dict[str, Any]:
    _ensure_dirs()
    if not os.path.exists(EASTER_EGGS_OVERRIDE):
        return {"filename": None, "set_at": None}
    try:
        with open(EASTER_EGGS_OVERRIDE, "r", encoding="utf-8") as f:
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


def _save_override(filename: str | None):
    _ensure_dirs()
    tmp = EASTER_EGGS_OVERRIDE + ".tmp"
    payload = {"filename": filename, "set_at": _utc_now_iso() if filename else None}
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    os.replace(tmp, EASTER_EGGS_OVERRIDE)


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/images")
def list_images():
    manifest = _sync_manifest_files(_load_manifest())
    _save_manifest(manifest)

    out = []
    for filename, meta in manifest["images"].items():
        prio = max(1, min(10, int(meta.get("priority", 5))))
        out.append({
            "filename": filename,
            "enabled": bool(meta.get("enabled", True)),
            "explicit": bool(meta.get("explicit", False)),
            "priority": prio,
            "uploaded_at": meta.get("uploaded_at"),
            "url": f"/eastereggs/{filename}",
        })
    out.sort(key=lambda x: x["filename"].lower())
    return {"images": out}


@router.post("/upload")
async def upload_image(file: UploadFile = File(...)):
    filename = _safe_filename(file.filename or "")
    if not _is_allowed_image(filename):
        raise HTTPException(status_code=400, detail="Unsupported file type")

    _ensure_dirs()
    dst = os.path.join(EASTER_EGGS_DIR, filename)
    tmp = dst + ".uploading"

    try:
        with open(tmp, "wb") as f:
            await file.seek(0)
            shutil.copyfileobj(file.file, f)
        os.replace(tmp, dst)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass

    manifest = _load_manifest()
    manifest.setdefault("images", {})[filename] = {
        "enabled": True, "explicit": False,
        "priority": 5, "uploaded_at": _utc_now_iso(),
    }
    _save_manifest(manifest)
    return {"ok": True, "filename": filename}


@router.delete("/images/{filename}")
def delete_image(filename: str):
    filename = _safe_filename(filename)
    path = os.path.join(EASTER_EGGS_DIR, filename)

    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {e}") from e

    manifest = _load_manifest()
    images = manifest.get("images", {})
    images.pop(filename, None)
    manifest["images"] = images
    _save_manifest(manifest)
    return {"ok": True, "filename": filename}


@router.post("/images/{filename}/enabled")
def set_enabled(filename: str, payload: dict[str, Any]):
    filename = _safe_filename(filename)
    enabled = bool(payload.get("enabled"))

    manifest = _sync_manifest_files(_load_manifest())
    images = manifest.setdefault("images", {})
    if filename not in images:
        raise HTTPException(status_code=404, detail="Image not found")

    images[filename]["enabled"] = enabled
    _save_manifest(manifest)
    return {"ok": True, "filename": filename, "enabled": enabled}


@router.post("/images/{filename}/explicit")
def set_explicit(filename: str, payload: dict[str, Any]):
    filename = _safe_filename(filename)
    explicit = bool(payload.get("explicit"))

    manifest = _sync_manifest_files(_load_manifest())
    images = manifest.setdefault("images", {})
    if filename not in images:
        raise HTTPException(status_code=404, detail="Image not found")

    if not isinstance(images[filename], dict):
        images[filename] = {
            "enabled": True, "explicit": explicit,
            "priority": 5, "uploaded_at": None,
        }
    else:
        images[filename]["explicit"] = explicit

    _save_manifest(manifest)
    return {"ok": True, "filename": filename, "explicit": explicit}


@router.post("/images/{filename}/priority")
def set_priority(filename: str, payload: dict[str, Any]):
    filename = _safe_filename(filename)
    prio = payload.get("priority")
    if prio is None:
        raise HTTPException(status_code=400, detail="Missing priority")
    try:
        prio_i = int(prio)
    except Exception as e:
        raise HTTPException(status_code=400, detail="priority must be an integer") from e
    prio_i = max(1, min(10, prio_i))

    manifest = _sync_manifest_files(_load_manifest())
    images = manifest.setdefault("images", {})
    if filename not in images:
        raise HTTPException(status_code=404, detail="Image not found")

    if not isinstance(images[filename], dict):
        images[filename] = {
            "enabled": True, "explicit": False,
            "priority": prio_i, "uploaded_at": None,
        }
    else:
        images[filename]["priority"] = prio_i

    _save_manifest(manifest)
    return {"ok": True, "filename": filename, "priority": prio_i}


@router.get("/override")
def get_override():
    data = _load_override()
    filename = data.get("filename")
    if filename:
        return {
            "filename": filename,
            "set_at": data.get("set_at"),
            "url": f"/eastereggs/{filename}",
        }
    return {"filename": None, "set_at": None}


@router.post("/override")
def set_override(payload: dict[str, Any]):
    filename = payload.get("filename", None)
    if filename is None:
        _save_override(None)
        return {"ok": True, "filename": None}

    if not isinstance(filename, str):
        raise HTTPException(status_code=400, detail="filename must be a string or null")

    filename = _safe_filename(filename)
    if not _is_allowed_image(filename):
        raise HTTPException(status_code=400, detail="Unsupported file type")

    path = os.path.join(EASTER_EGGS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Image not found on disk")

    _save_override(filename)
    return {"ok": True, "filename": filename, "url": f"/eastereggs/{filename}"}


@router.get("/settings")
def get_settings():
    settings = _load_settings()
    denom = int(settings.get("easter_egg_chance_denominator", 10))
    return {"easter_egg_chance_denominator": denom}


@router.post("/settings")
def set_settings(payload: dict[str, Any]):
    denom = payload.get("easter_egg_chance_denominator")
    if denom is None:
        raise HTTPException(status_code=400, detail="Missing easter_egg_chance_denominator")
    try:
        denom_i = int(denom)
    except Exception as e:
        raise HTTPException(status_code=400, detail="easter_egg_chance_denominator must be an integer") from e
    denom_i = max(0, denom_i)

    settings = dict(DEFAULT_SETTINGS)
    settings["easter_egg_chance_denominator"] = denom_i
    _save_settings(settings)
    return {"ok": True, "easter_egg_chance_denominator": denom_i}


@router.get("/live-preview")
def live_preview():
    if not os.path.exists(LIVE_STATE_PATH):
        return {"updated_at": None, "type": None, "filename": None, "url": None}
    try:
        with open(LIVE_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}

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


# ── Static file route for easter egg images ──────────────────────────

egg_router = APIRouter()


@egg_router.get("/eastereggs/{filename}")
def get_easteregg(filename: str):
    path = os.path.join(EASTER_EGGS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Image not found on disk")
    return FileResponse(path, media_type=_media_type(path))

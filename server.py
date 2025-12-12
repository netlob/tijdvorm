import os
import json
import shutil
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


EASTER_EGGS_DIR = os.path.abspath("./eastereggs")
MANIFEST_PATH = os.path.join(EASTER_EGGS_DIR, "manifest.json")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    os.makedirs(EASTER_EGGS_DIR, exist_ok=True)


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
            images[f] = {"enabled": True, "uploaded_at": None}

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


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/images")
def list_images() -> dict[str, Any]:
    manifest = _sync_manifest_files(_load_manifest())
    _save_manifest(manifest)

    out = []
    for filename, meta in manifest["images"].items():
        out.append(
            {
                "filename": filename,
                "enabled": bool(meta.get("enabled", True)),
                "uploaded_at": meta.get("uploaded_at"),
                "url": f"/eastereggs/{filename}",
            }
        )
    out.sort(key=lambda x: x["filename"].lower())
    return {"images": out}


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
    images[filename] = {"enabled": True, "uploaded_at": _utc_now_iso()}
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



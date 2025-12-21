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
OVERRIDE_PATH = os.path.join(EASTER_EGGS_DIR, "override.json")
SETTINGS_PATH = os.path.join(EASTER_EGGS_DIR, "settings.json")
TRIGGER_PATH = os.path.join(EASTER_EGGS_DIR, "trigger.json")

DEFAULT_SETTINGS: dict[str, Any] = {
    # 1 in N chance per cycle. Set to 0 to disable easter eggs.
    "easter_egg_chance_denominator": 10
}


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

def _save_trigger(reason: str) -> None:
    _ensure_dirs()
    tmp_path = TRIGGER_PATH + ".tmp"
    payload = {"reason": reason, "ts": _utc_now_iso()}
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    os.replace(tmp_path, TRIGGER_PATH)


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
            images[f] = {"enabled": True, "explicit": False, "uploaded_at": None}
        else:
            # Ensure new keys exist for older manifests
            if isinstance(images.get(f), dict):
                images[f].setdefault("explicit", False)
                images[f].setdefault("enabled", True)

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
                "explicit": bool(meta.get("explicit", False)),
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
        _save_trigger("override_cleared")
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
    _save_trigger("override_set")
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
    images[filename] = {"enabled": True, "explicit": False, "uploaded_at": _utc_now_iso()}
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
        images[filename] = {"enabled": True, "explicit": explicit, "uploaded_at": None}
    else:
        images[filename]["explicit"] = explicit

    _save_manifest(manifest)
    return {"ok": True, "filename": filename, "explicit": explicit}


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



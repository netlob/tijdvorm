import json
import os
from datetime import datetime, timezone
from tijdvorm.config import LIVE_DIR, LIVE_PREVIEW_FILENAME, LIVE_STATE_FILENAME

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


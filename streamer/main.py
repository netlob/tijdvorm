import os
import subprocess
import signal
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("streamer")

app = FastAPI(title="Tijdvorm Streamer")

BROWSER_PROCESS = None
# Common paths for Chromium on Pi/Linux
BROWSER_CMD = [
    "chromium-browser",
    "--kiosk",
    "--noerrdialogs",
    "--disable-infobars",
    "--check-for-update-interval=31536000",
    "--autoplay-policy=no-user-gesture-required"
]

class DisplayRequest(BaseModel):
    url: str

@app.post("/display")
def start_display(req: DisplayRequest):
    global BROWSER_PROCESS
    
    # 1. Stop existing
    stop_display()
    
    # 2. Start new
    logger.info(f"Starting display for URL: {req.url}")
    
    # Ensure DISPLAY is set (for Pi execution)
    env = os.environ.copy()
    if "DISPLAY" not in env:
        env["DISPLAY"] = ":0"
        
    cmd = BROWSER_CMD + [req.url]
    
    try:
        # Start new process group so we can kill it reliably
        BROWSER_PROCESS = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env
        )
        return {"status": "started", "pid": BROWSER_PROCESS.pid}
    except FileNotFoundError:
        logger.error("chromium-browser not found. Please install it (sudo apt install chromium-browser).")
        raise HTTPException(status_code=500, detail="chromium-browser binary not found")
    except Exception as e:
        logger.error(f"Failed to launch browser: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stop")
def stop_display():
    global BROWSER_PROCESS
    if BROWSER_PROCESS:
        logger.info("Stopping display...")
        if BROWSER_PROCESS.poll() is None:
            try:
                os.killpg(os.getpgid(BROWSER_PROCESS.pid), signal.SIGTERM)
                try:
                    BROWSER_PROCESS.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(os.getpgid(BROWSER_PROCESS.pid), signal.SIGKILL)
            except Exception as e:
                logger.error(f"Error stopping browser: {e}")
        BROWSER_PROCESS = None
    return {"status": "stopped"}

@app.get("/health")
def health():
    return {"status": "ok"}


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
# Command to launch X server with Chromium
# We use xinit to start X server + window manager + chromium
# This allows it to run on Lite without a desktop environment running
START_SCRIPT = os.path.abspath("start_kiosk.sh")

class DisplayRequest(BaseModel):
    url: str

@app.post("/display")
def start_display(req: DisplayRequest):
    global BROWSER_PROCESS
    
    # 1. Stop existing
    stop_display()
    
    # 2. Start new
    logger.info(f"Starting display for URL: {req.url}")
    
    # Create the start script dynamically or just pass URL to it
    # We will pass the URL as an argument to the start script
    
    try:
        # Start new process group so we can kill it reliably
        # We run 'xinit' which starts X and then our script
        # Note: We need to run this as the current user, assuming they have console rights (default on Pi)
        
        cmd = ["/usr/bin/xinit", START_SCRIPT, req.url, "--", "-nocursor"]
        
        BROWSER_PROCESS = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        return {"status": "started", "pid": BROWSER_PROCESS.pid}
    except FileNotFoundError:
        logger.error("xinit not found. Please run setup_pi.sh.")
        raise HTTPException(status_code=500, detail="xinit not found")
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
                # Killing xinit should kill the X server and children
                os.killpg(os.getpgid(BROWSER_PROCESS.pid), signal.SIGTERM)
                try:
                    BROWSER_PROCESS.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(os.getpgid(BROWSER_PROCESS.pid), signal.SIGKILL)
            except Exception as e:
                logger.error(f"Error stopping browser: {e}")
        BROWSER_PROCESS = None
    return {"status": "stopped"}

@app.get("/health")
def health():
    return {"status": "ok"}

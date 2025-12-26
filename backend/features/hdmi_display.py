import requests
import logging
from backend.config import STREAMER_HOST

logger = logging.getLogger(__name__)

def start_hdmi_display(url: str):
    """
    Sends a request to the remote Raspberry Pi streamer to launch the browser.
    """
    logger.info(f"Requesting HDMI display on {STREAMER_HOST} for URL: {url}")
    try:
        # Note: requests is sync, but we use it in a thread/bg task usually.
        # Ideally we'd use aiohttp if calling from async context, but this is simple enough for now.
        resp = requests.post(f"{STREAMER_HOST}/display", json={"url": url}, timeout=5)
        resp.raise_for_status()
        logger.info(f"Streamer started: {resp.json()}")
    except Exception as e:
        logger.error(f"Failed to start HDMI display on streamer: {e}")

def stop_hdmi_display():
    """
    Sends a request to the remote Raspberry Pi streamer to stop the browser.
    """
    logger.info(f"Requesting stop HDMI display on {STREAMER_HOST}...")
    try:
        resp = requests.post(f"{STREAMER_HOST}/stop", timeout=5)
        resp.raise_for_status()
        logger.info(f"Streamer stopped: {resp.json()}")
    except Exception as e:
        logger.error(f"Failed to stop HDMI display on streamer: {e}")


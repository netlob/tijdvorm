import asyncio
import json
import os
import socket
import logging
import pyatv
from backend.config import DATA_DIR

CREDENTIALS_FILE = os.path.join(DATA_DIR, "airplay_credentials.json")

# Configure logging
logger = logging.getLogger(__name__)

def get_local_ip():
    """Best effort to find the local IP address visible to the network."""
    try:
        # Create a dummy socket to connect to an external IP (doesn't send data)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

async def play_url_on_tv(url: str):
    """
    Connects to the TV using saved AirPlay credentials and plays the given URL.
    """
    if not os.path.exists(CREDENTIALS_FILE):
        logger.warning(f"AirPlay credentials not found at {CREDENTIALS_FILE}. Run scripts/pair_airplay.py first.")
        return False

    try:
        with open(CREDENTIALS_FILE, "r") as f:
            creds_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load AirPlay credentials: {e}")
        return False

    address = creds_data.get("address")
    credentials = creds_data.get("credentials")
    identifier = creds_data.get("identifier")
    
    if not address or not credentials:
        logger.error("Invalid AirPlay credentials file.")
        return False

    loop = asyncio.get_running_loop()
    
    # 1. Try scanning by IP
    logger.info(f"Scanning for AirPlay device at {address}...")
    results = await pyatv.scan(loop=loop, hosts=[address])
    
    device_conf = None
    
    if results:
        device_conf = results[0]
        logger.info(f"Found device by IP: {device_conf.name}")
    else:
        # 2. Fallback to general scan and match identifier or IP
        logger.info(f"Direct scan failed. Trying broadcast scan...")
        results = await pyatv.scan(loop=loop)
        for res in results:
            if str(res.address) == address:
                device_conf = res
                logger.info(f"Found device by broadcast IP match: {res.name}")
                break
            if identifier and res.identifier == identifier:
                device_conf = res
                logger.info(f"Found device by identifier match: {res.name}")
                break
    
    if not device_conf:
        logger.error(f"Could not find AirPlay device at {address}")
        return False
        
    device_conf.set_credentials(pyatv.Protocol.AirPlay, credentials)
    
    try:
        atv = await pyatv.connect(device_conf, loop=loop)
        try:
            # Play URL
            # Note: AirPlay usually expects HLS (.m3u8) or MP4/MOV. 
            # MJPEG support is experimental/device dependent.
            await atv.stream.play_url(url)
            logger.info(f"Sent Play URL command to TV: {url}")
        finally:
            try:
                await atv.close()
            except Exception as e:
                logger.debug(f"atv.close() failed (ignoring): {e}")
            
        return True
    except Exception as e:
        logger.error(f"Failed to stream via AirPlay: {e}")
        return False

async def stop_airplay():
    """Stops playback."""
    if not os.path.exists(CREDENTIALS_FILE):
        return

    try:
        with open(CREDENTIALS_FILE, "r") as f:
            creds_data = json.load(f)
    except Exception:
        return

    address = creds_data.get("address")
    credentials = creds_data.get("credentials")
    
    loop = asyncio.get_running_loop()
    # Use general scan for cleanup as it is more robust to IP changes if using ID logic (though here we just use IP)
    # Actually, let's keep it simple for stop - try IP first
    results = await pyatv.scan(loop=loop, hosts=[address])
    
    if not results:
        # Try broadcast
        results = await pyatv.scan(loop=loop)
        # Filter logic duplicated but simple enough
        device_conf = None
        for res in results:
             if str(res.address) == address:
                 device_conf = res
                 break
        if not device_conf:
            return
    else:
        device_conf = results[0]

    device_conf.set_credentials(pyatv.Protocol.AirPlay, credentials)
    
    try:
        atv = await pyatv.connect(device_conf, loop=loop)
        # Stop is usually done by navigating or stream interface
        # but play_url doesn't return a controller that persists easily without keeping connection open.
        # But we can try stop() on remote control interface if available.
        # or just stream.stop() if supported.
        # atv.stream does not have stop().
        # atv.remote_control.stop() might work.
        pass # Not implemented yet as 'stop' behavior for play_url is tricky without keeping state.
        try:
            await atv.close()
        except Exception:
            pass
    except Exception:
        pass


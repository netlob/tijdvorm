import os
import sys

# Add project root to sys.path to allow imports from backend.*
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time
import random
import logging
import asyncio
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from backend.config import TV_IP, TV_IPS, UPDATE_INTERVAL_MINUTES
from backend.integrations.samsung import is_tv_reachable, connect_to_tv, update_tv_art, select_tv_art, _delete_old_user_art
from backend.integrations.home_assistant import get_sauna_status, is_doorbell_active
from backend.features.easter_eggs import (
    get_override_image_path, get_cached_content_id, set_cached_content_id,
    preserved_content_ids, prepare_rotated_image, load_easter_egg_settings,
    get_random_easter_egg_filtered
)
from backend.features.sauna import generate_sauna_image
from backend.features.timeform import generate_timeform_image
from backend.features.preview import write_live_preview

# --- Main Loop (Async) ---

async def interruptible_sleep_async(interval_minutes, current_override_path):
    """
    Sleeps until the next interval minute, but checks for override changes every second.
    Returns True if interrupted by override change, False otherwise.
    """
    current_time = time.time()
    seconds_past_minute = current_time % 60
    sleep_seconds = (interval_minutes * 60) - seconds_past_minute
    
    # If we are very close to the minute boundary, push to next interval
    if sleep_seconds < 1:
        sleep_seconds += (interval_minutes * 60)

    print(f"===== Cycle finished. Sleeping for {sleep_seconds:.2f} seconds until next minute... ====")

    end_time = time.time() + sleep_seconds
    while time.time() < end_time:
        # Check if override changed
        new_override = get_override_image_path()
        if new_override != current_override_path:
            print(f"Override changed (Old: {current_override_path}, New: {new_override}). Waking up immediately.")
            return True
        
        # Sleep small amount
        remaining = end_time - time.time()
        await asyncio.sleep(min(1.0, remaining))
    
    return False

async def main_loop(tv_ips, interval_minutes):
    """Runs the image generation and TV update periodically."""
    logging.basicConfig(level=logging.INFO)
    print(f"Starting main loop. TV IPs: {tv_ips}, Update Interval: {interval_minutes} minutes.")
    
    tv = False
    current_ip = None

    async def connect_any():
        for ip in tv_ips:
            if is_tv_reachable(ip):
                print(f"TV at {ip} is reachable. Connecting...")
                try:
                    conn = await connect_to_tv(ip)
                    print(f"Connected to TV at {ip}.")
                    return conn, ip
                except Exception as e:
                    print(f"Failed to connect to {ip}: {e}")
        return False, None

    # Initial connection
    tv, current_ip = await connect_any()
    if not tv:
         print("Initial connection failed. Will retry in loop.")

    iteration = 1
    while True:
        # 1. Check Doorbell Active State
        # If doorbell is active, we PAUSE everything. HA is handling the TV.
        if is_doorbell_active():
            print("===== Doorbell is ACTIVE (controlled by HA). Pausing TV updates... =====")
            await asyncio.sleep(5) # Check again in 5s
            continue

        # Check reachability / Maintain connection
        # If we have a current IP, check if it's still reachable
        if current_ip and not is_tv_reachable(current_ip):
            print(f"\n===== TV at {current_ip} is unreachable. Lost connection. =====")
            tv = False 

        # If disconnected or periodic reconnect
        if iteration % 10 == 0 or tv is False:
            if iteration % 10 == 0 and tv:
                print(f"Periodic reconnection to {current_ip}...")
                try:
                    await tv.close()
                except:
                    pass
                # Try reconnecting to same IP first
                if is_tv_reachable(current_ip):
                    try:
                        tv = await connect_to_tv(current_ip)
                    except Exception as e:
                        print(f"Reconnect failed: {e}")
                        tv = False
                else:
                    tv = False # Force scan
            
            if tv is False:
                print("Scanning for TV connection...")
                tv, new_ip = await connect_any()
                if tv:
                    current_ip = new_ip
                else:
                    print("Could not connect to any TV. Sleeping 10s...")
                    await asyncio.sleep(10)
                    continue

        print(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} - Running Update Cycle {iteration} (IP: {current_ip}) ====")
        try:
            if tv is False:
                print("Failed to connect to TV. Skipping update.")
                continue

            # Determine which image to show
            override_path = get_override_image_path()
            if override_path:
                print(f"Override active: {override_path}")
                override_filename = os.path.basename(override_path)
                preserve = preserved_content_ids()
                cached_id = get_cached_content_id(override_filename)
                # Always generate a rotated preview image for the web UI
                rotated_for_preview = prepare_rotated_image(override_path)
                if cached_id:
                    print(f"Reusing cached TV content_id for override: {cached_id}")
                    ok = await select_tv_art(tv, cached_id, preserve_ids=preserve)
                    if ok and rotated_for_preview:
                        write_live_preview(rotated_for_preview, {"type": "override", "filename": override_filename})
                    iteration += 1
                    # Sleep until next cycle (interruptible)
                    await interruptible_sleep_async(interval_minutes, override_path)
                    continue
                else:
                    # First time: upload once and cache content_id
                    image_path = rotated_for_preview
                    live_meta = {"type": "override", "filename": override_filename}
            else:
                image_path = None

            # Easter egg frequency: 1 in N chance (configured via eastereggs/settings.json)
            settings = load_easter_egg_settings()
            denom = int(settings.get("easter_egg_chance_denominator", 10))
            is_easter_egg = False
            if denom <= 0:
                is_easter_egg = False
            elif denom == 1:
                is_easter_egg = True
            else:
                is_easter_egg = random.randint(1, denom) == 1

            if (not image_path) and is_easter_egg:
                print(f"It's Easter Egg time! (1/{denom} chance hit)")
                egg_path = get_random_easter_egg_filtered()
                if egg_path:
                     print(f"Selected easter egg: {egg_path}")
                     egg_filename = os.path.basename(egg_path)
                     preserve = preserved_content_ids()
                     cached_id = get_cached_content_id(egg_filename)
                     rotated_for_preview = prepare_rotated_image(egg_path)
                     if cached_id:
                         print(f"Reusing cached TV content_id for easteregg: {cached_id}")
                         ok = await select_tv_art(tv, cached_id, preserve_ids=preserve)
                         if ok and rotated_for_preview:
                             write_live_preview(rotated_for_preview, {"type": "easteregg", "filename": egg_filename})
                         iteration += 1
                         await interruptible_sleep_async(interval_minutes, override_path)
                         continue
                     else:
                         image_path = rotated_for_preview
                         live_meta = {"type": "easteregg", "filename": egg_filename}
                else:
                     print("No easter eggs found. Falling back to Timeform.")

            # If not easter egg or easter egg failed, generate Timeform/Sauna
            if not image_path:
                
                # Check Sauna Status
                sauna_status = get_sauna_status()
                
                if sauna_status and sauna_status.get('is_on'):
                     image_path = await generate_sauna_image(sauna_status)
                     live_meta = {"type": "sauna", "filename": os.path.basename(image_path) if image_path else None}
                else:
                    # Run the async image generation (Timeform)
                    image_path = await generate_timeform_image()
                    live_meta = {"type": "timeform", "filename": os.path.basename(image_path) if image_path else None}

            if image_path:
                # Run the synchronous TV update
                preserve = preserved_content_ids()
                new_id = await update_tv_art(tv, image_path, preserve_ids=preserve)
                if new_id:
                    # Cache content_id only for eastereggs/override (files under eastereggs/)
                    try:
                        if live_meta.get("type") in ("easteregg", "override") and live_meta.get("filename"):
                            set_cached_content_id(live_meta["filename"], new_id)
                    except Exception:
                        pass
                    write_live_preview(image_path, live_meta if "live_meta" in locals() else {"type": None, "filename": None})
            else:
                print("Image generation/selection failed, skipping TV update.")

        except Exception as e:
            print(f"Error in main loop cycle: {e}")

        # Calculate seconds until the next minute (interruptible)
        await interruptible_sleep_async(interval_minutes, override_path)
        iteration += 1

if __name__ == "__main__":
    # Ensure TV_IP is set correctly before running!
    if TV_IP == "192.168.1.100":
       print("\n!!! WARNING: TV_IP is set to the default placeholder.")
       print("!!! Please edit the script and set TV_IP to your Samsung Frame TV's actual IP address.\n")
       # exit(1) # Optional: Uncomment to prevent running with placeholder
    # update_tv_art(TV_IP, '/Users/sjoerdbolten/Documents/Projects/tijdvorm/py/timeform_art.png')
    asyncio.run(main_loop(TV_IPS, UPDATE_INTERVAL_MINUTES))

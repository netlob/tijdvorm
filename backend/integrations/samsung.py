import platform
import subprocess
import os
import asyncio
from samsungtvws.async_art import SamsungTVAsyncArt
from samsungtvws import exceptions, SamsungTVWS
from backend.config import DELETE_OLD_ART, DATA_DIR

# Store token in data directory so it persists
TOKEN_FILE = os.path.join(DATA_DIR, "tv_token.txt")

def is_tv_reachable(ip):
    """Pings the TV to check if it is reachable."""
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = ['ping', param, '1', ip]
    try:
        return subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except Exception:
        return False

async def connect_to_tv(tv_ip):
    """Connects to TV using Async API."""
    print(f"Connecting to TV at {tv_ip}...")
    try:
        tv = SamsungTVAsyncArt(host=tv_ip, port=8002, token_file=TOKEN_FILE)
        await tv.start_listening()

        # check if art mode is supported
        supported = await tv.supported()
        if supported:
            print("Connected and Art Mode supported.")
            return tv
        else:
            print("Connected but Art Mode NOT supported.")
            await tv.close()
            return None
    except Exception as e:
        print(f"Failed to connect: {e}")
        return None

async def _delete_old_user_art(tv, keep_ids):
    """Deletes TV 'MY_' art except IDs in keep_ids."""
    try:
        try:
            available_art = await tv.available()
        except AssertionError:
            available_art = []
            
        if not available_art:
            return

        # available_art is a list of dicts
        user_art_ids = [art["content_id"] for art in available_art if art.get("content_id", "").startswith("MY_")]
        ids_to_delete = [art_id for art_id in user_art_ids if art_id not in keep_ids]
        ids_to_delete = list(set(ids_to_delete))
        
        if ids_to_delete and DELETE_OLD_ART:
            print(f"Deleting {len(ids_to_delete)} old user art pieces (keeping {len(keep_ids)} cached): {ids_to_delete}")
            await tv.delete_list(ids_to_delete)
            
    except Exception as e:
        print(f"Warning: cleanup failed ({e})")

async def update_tv_art(tv, image_path, preserve_ids=None):
    """Uploads image, selects it, then deletes old art while preserving cached IDs."""
    print(f"--- Starting TV Update (Async) --- ")
    try:
        preserve_ids = set(preserve_ids or [])
        
        # 1. Ensure Art Mode is On
        try:
            print("Ensuring Art Mode is ON...")
            await tv.set_artmode('on')
            print("Set Art Mode command sent.")
        except Exception as e_artmode:
            print(f"Warning: Could not set Art Mode: {e_artmode}")

        # 2. Upload new art
        print(f"Uploading image file: {image_path}")
        
        # Using filename upload method
        upload_result = await tv.upload(image_path, matte='none', portrait_matte='none')
        
        if not upload_result:
             print("Error: Failed to upload image or get content_id.")
             return None
        
        # upload_result is content_id (string)
        new_content_id = upload_result
        print(f"Image uploaded successfully. New Content ID: {new_content_id}")

        # 3. Select the new art
        print(f"Selecting new image: {new_content_id}")
        await tv.select_image(new_content_id, show=True)
        print("Selection command sent.")
        
        # Cleanup old art
        preserve_ids.add(new_content_id)
        await _delete_old_user_art(tv, preserve_ids)

        print("--- TV Update Finished ---")
        return new_content_id

    except Exception as e:
        print(f"Error during TV interaction: {e}")
        print("--- TV Update Failed ---")
        return None

async def select_tv_art(tv, content_id, preserve_ids=None):
    """Select a previously uploaded piece of TV art, then cleanup while preserving cached IDs."""
    try:
        preserve_ids = set(preserve_ids or [])
        await tv.set_artmode('on')
        await tv.select_image(content_id, show=True)
        
        preserve_ids.add(content_id)
        await _delete_old_user_art(tv, preserve_ids)
        return True
    except Exception as e:
        print(f"Warning: failed to select cached art {content_id} ({e})")
        return False

async def switch_to_hdmi(tv_ip, source_key):
    """Switches TV to HDMI source using remote control commands."""
    print(f"Switching TV at {tv_ip} to HDMI ({source_key})...")
    def _switch():
        try:
            # Standard remote control connection
            # We use the same token file to avoid re-auth prompts
            tv = SamsungTVWS(host=tv_ip, port=8002, token_file=TOKEN_FILE)
            tv.send_key(source_key)
        except Exception as e:
            print(f"Failed to switch to HDMI: {e}")

    await asyncio.to_thread(_switch)

async def set_art_mode_active(tv_ip, active: bool = True):
    """
    Sets Art Mode state. 
    active=True -> Art Mode
    active=False -> Exit Art Mode (usually goes to TV)
    """
    try:
        tv = await connect_to_tv(tv_ip)
        if tv:
            state = 'on' if active else 'off'
            print(f"Setting Art Mode to {state}...")
            await tv.set_artmode(state)
            await tv.close()
    except Exception as e:
        print(f"Failed to set Art Mode {active}: {e}")

import platform
import subprocess
from samsungtvws import SamsungTVWS
from backend.config import DELETE_OLD_ART

def is_tv_reachable(ip):
    """Pings the TV to check if it is reachable."""
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = ['ping', param, '1', ip]
    try:
        return subprocess.call(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except Exception:
        return False

def connect_to_tv(tv_ip):
    """Connects to TV, uploads image, cleans old, selects new."""
    print(f"Connecting to TV...")
    try:
        tv = SamsungTVWS(tv_ip)

        # check if art mode is supported
        art_info = tv.art().supported()
        if art_info is True:
            print("Connected.")
            return tv
        return False
    except Exception as e:
        print(f"Failed to connect: {e}")
        return False

def _delete_old_user_art(tv, keep_ids):
    """Deletes TV 'MY_' art except IDs in keep_ids."""
    try:
        available_art = tv.art().available()
        if not available_art:
            return
        user_art_ids = [art["content_id"] for art in available_art if art.get("content_id", "").startswith("MY_")]
        ids_to_delete = [art_id for art_id in user_art_ids if art_id not in keep_ids]
        ids_to_delete = list(set(ids_to_delete))
        if ids_to_delete and DELETE_OLD_ART:
            print(f"Deleting {len(ids_to_delete)} old user art pieces (keeping {len(keep_ids)} cached): {ids_to_delete}")
            tv.art().delete_list(ids_to_delete)
    except Exception as e:
        print(f"Warning: cleanup failed ({e})")

def update_tv_art(tv, image_path, preserve_ids=None):
    """Uploads image, selects it, then deletes old art while preserving cached IDs."""
    print(f"--- Starting TV Update --- ")
    try:
        preserve_ids = set(preserve_ids or [])
        # 1. Ensure Art Mode is On
        try:
            print("Ensuring Art Mode is ON...")
            tv.art().set_artmode(True)
            print("Set Art Mode command sent.")
        except Exception as e_artmode:
            print(f"Warning: Could not set Art Mode (may already be on or TV off): {e_artmode}")

        # 2. Upload new art
        print(f"Reading image file: {image_path}")
        with open(image_path, 'rb') as f:
            image_data = f.read()
        
        print("Uploading new image...")
        upload_result = tv.art().upload(image_data, matte='none', portrait_matte='none') # Specify PNG
        
        if not upload_result:
             print("Error: Failed to upload image or get content_id.")
             return False
        
        new_content_id = upload_result
        print(f"Image uploaded successfully. New Content ID: {new_content_id}")

        # 3. Select the new art
        print(f"Selecting new image: {new_content_id}")
        tv.art().select_image(new_content_id, show=True)
        print("Selection command sent.")
        # Cleanup old art, but keep cached eastereggs + current
        preserve_ids.add(new_content_id)
        _delete_old_user_art(tv, preserve_ids)

        print("--- TV Update Finished ---")
        return new_content_id

    except Exception as e:
        print(f"Error during TV interaction: {e}")
        print("--- TV Update Failed ---")
        return None

def select_tv_art(tv, content_id, preserve_ids=None):
    """Select a previously uploaded piece of TV art, then cleanup while preserving cached IDs."""
    try:
        preserve_ids = set(preserve_ids or [])
        tv.art().set_artmode(True)
        tv.art().select_image(content_id, show=True)
        preserve_ids.add(content_id)
        _delete_old_user_art(tv, preserve_ids)
        return True
    except Exception as e:
        print(f"Warning: failed to select cached art {content_id} ({e})")
        return False


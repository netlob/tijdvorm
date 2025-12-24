import asyncio
from playwright.async_api import async_playwright
from PIL import Image, ImageDraw, ImageFont
import io
import os
import time
import random
import requests
import logging
import platform
import subprocess
import json
from datetime import datetime, timezone

from samsungtvws import SamsungTVWS

# --- Samsung TV Config ---
TV_IP = "10.0.1.111" # !!! REPLACE WITH YOUR TV's IP ADDRESS !!!
UPDATE_INTERVAL_MINUTES = 1
DELETE_OLD_ART = True # turn on to always delete all manually uploaded art
# TODO: tag & only delete old "timefroms" art, not user uploaded art

# --- Configuration Constants ---
WEATHER_LOCATION = "Amsterdam,NL"
URL = "https://timeforms.app"

# Selectors
ARTWORK_FRAME_SELECTOR = "#root > div.w-full.min-h-screen.flex.items-center.justify-center.p-8.transition-colors.duration-1000.relative > div.absolute.top-1\\/2.left-1\\/2.-translate-y-1\\/2.-translate-x-1\\/2.w-full.flex.justify-center.items-center > div > div"
SLIDER_TRACK_SELECTOR = 'span.relative.flex.touch-none.select-none.items-center.w-full.slider-custom'

# Output
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FILENAME = "timeform_art.png"
EASTER_EGGS_DIR = "./eastereggs"
EASTER_EGGS_MANIFEST = os.path.join(EASTER_EGGS_DIR, "manifest.json")
EASTER_EGGS_OVERRIDE = os.path.join(EASTER_EGGS_DIR, "override.json")
EASTER_EGGS_SETTINGS = os.path.join(EASTER_EGGS_DIR, "settings.json")

LIVE_DIR = "./live"
LIVE_PREVIEW_FILENAME = "preview.png"
LIVE_STATE_FILENAME = "state.json"


def _load_egg_manifest():
    try:
        if not os.path.exists(EASTER_EGGS_MANIFEST):
            return {"version": 1, "images": {}}
        with open(EASTER_EGGS_MANIFEST, "r", encoding="utf-8") as f:
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


def _save_egg_manifest(manifest):
    try:
        os.makedirs(EASTER_EGGS_DIR, exist_ok=True)
        tmp_path = EASTER_EGGS_MANIFEST + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)
        os.replace(tmp_path, EASTER_EGGS_MANIFEST)
    except Exception as e:
        print(f"Warning: failed to save manifest.json ({e})")


def _get_cached_content_id(filename):
    manifest = _load_egg_manifest()
    images = manifest.get("images", {})
    meta = images.get(filename)
    if isinstance(meta, dict):
        cid = meta.get("tv_content_id")
        if isinstance(cid, str) and cid:
            return cid
    return None


def _set_cached_content_id(filename, content_id):
    manifest = _load_egg_manifest()
    images = manifest.setdefault("images", {})
    meta = images.get(filename)
    if not isinstance(meta, dict):
        meta = {"enabled": True, "explicit": False, "priority": 5, "uploaded_at": None}
    meta["tv_content_id"] = content_id
    images[filename] = meta
    manifest["images"] = images
    _save_egg_manifest(manifest)


def _preserved_content_ids():
    """All cached easteregg/override content IDs that should never be deleted."""
    manifest = _load_egg_manifest()
    images = manifest.get("images", {})
    keep = set()
    if isinstance(images, dict):
        for _, meta in images.items():
            if not isinstance(meta, dict):
                continue
            cid = meta.get("tv_content_id")
            if isinstance(cid, str) and cid:
                keep.add(cid)
    return keep


def _delete_old_user_art(tv, keep_ids):
    """Deletes TV 'MY_' art except IDs in keep_ids."""
    try:
        available_art = tv.art().available()
        if not available_art:
            return
        user_art_ids = [art["content_id"] for art in available_art if art.get("content_id", "").startswith("MY_")]
        ids_to_delete = [art_id for art_id in user_art_ids if art_id not in keep_ids]
        if ids_to_delete and DELETE_OLD_ART:
            print(f"Deleting {len(ids_to_delete)} old user art pieces (keeping {len(keep_ids)} cached): {ids_to_delete}")
            tv.art().delete_list(ids_to_delete)
    except Exception as e:
        print(f"Warning: cleanup failed ({e})")

# Home Assistant explicit toggle (read at easter-egg time)
HA_EXPLICIT_ENTITY = os.environ.get("HA_EXPLICIT_ENTITY", "input_boolean.explicit_frame_art")
HA_SAUNA_ENTITY = os.environ.get("HA_SAUNA_ENTITY", "climate.sauna_control")
HA_BASE_URL = os.environ.get("HA_BASE_URL", "").rstrip("/")  # e.g. https://ha.example.com
HA_TOKEN = os.environ.get("HA_TOKEN", "")
HA_TIMEOUT_SECONDS = float(os.environ.get("HA_TIMEOUT_SECONDS", "2.0"))
HA_CACHE_TTL_SECONDS = float(os.environ.get("HA_CACHE_TTL_SECONDS", "30.0"))

# Playwright Timing
PAGE_LOAD_TIMEOUT = 90000
SELECTOR_TIMEOUT = 60000
RENDER_WAIT_TIME = 3 # Seconds to wait after page actions for rendering

# Simulation
SIMULATE_HOUR = None# Set hour (0-23) or None

# Weather API
MODIFIED_WEATHER_URL = f"https://api.weatherapi.com/v1/current.json?key=8cd71ded6ce646e888600951251504&q={WEATHER_LOCATION}"

# Font Configuration
FONT_PATH = "./fonts/SFNS.ttf"
TEMP_FONT_SIZE = 63
COND_FONT_SIZE = 47
TIME_FONT_SIZE = 39
TEXT_COLOR = (75, 85, 99)
TEXT_PADDING = 75
LINE_SPACING = 26

# Image Processing
CROP_LEFT = 90
CROP_RIGHT_MARGIN = 90
CROP_TOP = 192
CROP_BOTTOM_MARGIN = 192
ZOOM_FACTOR = 1.15
COLOR_TOLERANCE = 30

# CSS Injection
HIDE_CSS = """
  .fixed.top-8.left-8.text-2xl,
  .fixed.bottom-8.left-8.text-xs,
  .fixed.left-8.top-1\\/2.-translate-y-1\\/2,
  .fixed.left-8.z-50,
  .fixed.bottom-0.left-0.right-0.w-full.z-50,
  .absolute.bottom-6.left-6.text-gray-600.z-30,
  span.relative.flex.touch-none.select-none.items-center.w-full.slider-custom,
  button:has(svg.lucide-play),
  button:has(svg.lucide-rotate-ccw) {
    display: none !important;
  }
"""



# --- Helper Functions ---

def color_diff(color1, color2):
    """Calculate the sum of absolute differences between two RGB tuples."""
    if not color1 or not color2 or len(color1) < 3 or len(color2) < 3:
        return float('inf')
    return sum(abs(c1 - c2) for c1, c2 in zip(color1[:3], color2[:3]))

def get_weather_data(url):
    """Fetch weather data JSON from the specified URL."""
    print(f"Fetching weather data from: {url}")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        print("Weather data fetched successfully.")
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching weather data: {e}")
        return None

def load_font_with_fallback(font_path, size):
    """Load font from a specific path, falling back to Pillow default."""
    abs_path = os.path.abspath(font_path)
    print(f"[Font Load] Attempting to load: {abs_path}")
    try:
        font = ImageFont.truetype(abs_path, size)
        print(f"[Font Load] Successfully loaded: {abs_path}")
        return font
    except IOError as e:
        print(f"[Font Load] Warning: IOError loading '{abs_path}': {e}. Using default Pillow font.")
        try:
            font = ImageFont.load_default()
            print(f"[Font Load] Loaded default Pillow font instead.")
            return font
        except IOError as e2:
            print(f"[Font Load] Error: Could not load even the default Pillow font: {e2}")
            return None
    except Exception as e:
        print(f"[Font Load] Unexpected error loading font '{abs_path}': {e}")
        return None

def load_fonts():
    """Load all required fonts using the specified path."""
    print("Loading fonts...")
    fonts = {
        'font_temp': load_font_with_fallback(FONT_PATH, TEMP_FONT_SIZE),
        'font_cond': load_font_with_fallback(FONT_PATH, COND_FONT_SIZE),
        'font_time': load_font_with_fallback(FONT_PATH, TIME_FONT_SIZE)
    }
    return fonts

async def take_screenshot():
    """Launch browser, navigate, capture screenshot, and return bytes."""
    print("Launching browser...")
    screenshot_bytes = None
    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch()
        except Exception as e:
            print(f"Failed Chromium: {e}. Trying Firefox...")
            try: browser = await p.firefox.launch()
            except Exception as e2: print(f"Failed Firefox: {e2}"); return None
        if not browser: return None

        page = await browser.new_page(viewport={"width": OUTPUT_WIDTH, "height": OUTPUT_HEIGHT})
        try:
            print(f"Navigating to {URL}...")
            await page.goto(URL, timeout=PAGE_LOAD_TIMEOUT, wait_until='networkidle')
            print("Page navigation complete.")

            # Time Simulation (if enabled)
            if SIMULATE_HOUR is not None and 0 <= SIMULATE_HOUR <= 23:
                print(f"Simulating time: {SIMULATE_HOUR}:00")
                try:
                    slider_track = page.locator(SLIDER_TRACK_SELECTOR)
                    await slider_track.wait_for(state="visible", timeout=SELECTOR_TIMEOUT)
                    bbox = await slider_track.bounding_box()
                    if bbox:
                        click_x = bbox['x'] + (SIMULATE_HOUR / 23) * bbox['width']
                        click_y = bbox['y'] + bbox['height'] / 2
                        await page.mouse.click(click_x, click_y)
                        await asyncio.sleep(1) # Wait for simulation effect
                except Exception as e: print(f"Error interacting with slider: {e}")
            else: print("Using current time.")

            # Inject CSS
            try: await page.add_style_tag(content=HIDE_CSS); print("CSS injected.")
            except Exception as e: print(f"Error injecting CSS: {e}")

            # Wait for artwork frame and rendering
            try:
                await page.locator(ARTWORK_FRAME_SELECTOR).wait_for(state='visible', timeout=SELECTOR_TIMEOUT)
                print("Artwork frame found. Waiting for rendering...")
                await asyncio.sleep(RENDER_WAIT_TIME)
            except Exception as e: print(f"Error finding frame: {e}"); return None

            # Take Screenshot
            try: screenshot_bytes = await page.screenshot(); print("Screenshot taken.")
            except Exception as e: print(f"Error taking screenshot: {e}"); return None

        except Exception as e:
            print(f"Error during browser interaction: {e}")
        finally:
            await browser.close()
            print("Browser closed.")
    
    return screenshot_bytes

def process_screenshot(screenshot_bytes):
    """Crop, get colors, zoom, create canvas, align, and paste."""
    print("Processing screenshot...")
    try:
        img = Image.open(io.BytesIO(screenshot_bytes))
    except Exception as e:
        print(f"Error opening screenshot bytes: {e}"); return None, True # Default align top

    # Crop
    try:
        crop_box = (CROP_LEFT, CROP_TOP, img.width - CROP_RIGHT_MARGIN, img.height - CROP_BOTTOM_MARGIN)
        if crop_box[0] >= crop_box[2] or crop_box[1] >= crop_box[3]: raise ValueError("Invalid crop dimensions")
        cropped_img = img.crop(crop_box)
        cropped_w, cropped_h = cropped_img.size
        print(f"Cropped image size: {cropped_w}x{cropped_h}")
    except Exception as e: print(f"Error cropping image: {e}"); return None, True

    # Get Colors
    top_left_color = (255, 255, 255); top_center_color = (255, 255, 255); dynamic_bg_color = top_left_color
    try:
        top_left_color_raw = cropped_img.getpixel((0, 0))
        top_left_color = top_left_color_raw[:3] if len(top_left_color_raw) == 4 else top_left_color_raw
        dynamic_bg_color = top_left_color
        center_x = cropped_w // 2
        top_center_color_raw = cropped_img.getpixel((center_x, 0))
        top_center_color = top_center_color_raw[:3] if len(top_center_color_raw) == 4 else top_center_color_raw
    except Exception as e: print(f"Warning: Could not get pixel colors: {e}.")

    # Zoom
    scaled_w = int(cropped_w * ZOOM_FACTOR)
    scaled_h = int(cropped_h * ZOOM_FACTOR)
    scaled_img = cropped_img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

    # Create Background
    background = Image.new('RGB', (OUTPUT_WIDTH, OUTPUT_HEIGHT), dynamic_bg_color)
    print(f"Created background canvas with color {dynamic_bg_color}")

    # Determine Alignment
    offset_x = (OUTPUT_WIDTH - scaled_w) // 2
    diff = color_diff(top_left_color, top_center_color)
    align_to_top = diff > COLOR_TOLERANCE
    offset_y = 0 if align_to_top else (OUTPUT_HEIGHT - scaled_h)
    alignment_desc = "top" if align_to_top else "bottom"
    print(f"Aligning artwork to {alignment_desc} (color diff: {diff})")

    # Paste Artwork
    background.paste(scaled_img, (offset_x, offset_y))

    return background, align_to_top

def add_text_overlay(image, text_data, fonts, align_artwork_top):
    """Draw text overlay onto the image based on alignment."""
    if not image: return None
    print("Adding text overlay...")
    
    # Convert to RGBA to support opacity
    image = image.convert('RGBA')
    draw = ImageDraw.Draw(image)
    
    temp_str = text_data.get('temp', '--°C')
    cond_str = text_data.get('condition', 'Unknown')
    time_str = time.strftime("%H:%M")

    # Sauna Text Logic
    sauna_data = text_data.get('sauna')
    sauna_current_str = None
    sauna_set_str = None
    if sauna_data and sauna_data.get('is_on'):
        try:
            cur = float(sauna_data.get('current_temp', 0))
            tgt = float(sauna_data.get('set_temp', 0))
            sauna_current_str = f"Sauna: {cur:.0f}°C"
            sauna_set_str = f" / {tgt:.0f}°C"
        except Exception:
            pass

    # Get the single font type loaded for different sizes
    font_temp = fonts.get('font_temp')
    font_cond = fonts.get('font_cond')
    font_time = fonts.get('font_time')
    
    print(f"[Text Draw] Font for Temp: {font_temp}")
    print(f"[Text Draw] Font for Cond: {font_cond}")
    print(f"[Text Draw] Font for Time: {font_time}")

    # Calculate text block height (more robustly)
    bbox_temp_h, bbox_cond_h, bbox_time_h = TEMP_FONT_SIZE, COND_FONT_SIZE, TIME_FONT_SIZE
    try:
        if font_temp: bbox_temp_h = draw.textbbox((0, 0), temp_str, font=font_temp)[3] - draw.textbbox((0, 0), temp_str, font=font_temp)[1]
        if font_cond: bbox_cond_h = draw.textbbox((0, 0), cond_str, font=font_cond)[3] - draw.textbbox((0, 0), cond_str, font=font_cond)[1]
        if time_str and font_time: bbox_time_h = draw.textbbox((0, 0), time_str, font=font_time)[3] - draw.textbbox((0, 0), time_str, font=font_time)[1]
    except Exception as e: print(f"Warning: Error calculating text height: {e}")

    text_block_height = bbox_temp_h + LINE_SPACING + bbox_cond_h
    
    # Add sauna height
    bbox_sauna_h = 0
    if sauna_current_str and font_cond:
         bbox_sauna_h = COND_FONT_SIZE 
         try:
             bbox_sauna_h = draw.textbbox((0, 0), sauna_current_str, font=font_cond)[3] - draw.textbbox((0, 0), sauna_current_str, font=font_cond)[1]
         except Exception: pass
         text_block_height += LINE_SPACING + bbox_sauna_h
         
    if time_str: text_block_height += LINE_SPACING + bbox_time_h

    # Determine text Y position (using user's padding multiplier)
    text_padding_y = TEXT_PADDING * 1.5
    text_at_top = not align_artwork_top
    text_y = text_padding_y if text_at_top else (OUTPUT_HEIGHT - text_block_height - text_padding_y)
    position_desc = "top-left" if text_at_top else "bottom-left"
    print(f"Drawing text at {position_desc} (y={text_y:.0f})")

    # Draw text lines (using user's spacing multiplier for first gap)
    current_y = text_y
    text_padding_x = TEXT_PADDING
    try:
        if font_temp:
            draw.text((text_padding_x, current_y), temp_str, font=font_temp, fill=TEXT_COLOR)
            current_y += bbox_temp_h + (LINE_SPACING * 1.3)
        if font_cond:
            draw.text((text_padding_x, current_y), cond_str, font=font_cond, fill=TEXT_COLOR)
            current_y += bbox_cond_h + LINE_SPACING
        
        # Draw Sauna
        if sauna_current_str and font_cond:
            draw.text((text_padding_x, current_y), sauna_current_str, font=font_cond, fill=TEXT_COLOR)
            if sauna_set_str:
                w_current = draw.textlength(sauna_current_str, font=font_cond)
                text_color_half = list(TEXT_COLOR) + [128]
                draw.text((text_padding_x + w_current, current_y), sauna_set_str, font=font_cond, fill=tuple(text_color_half))
            current_y += bbox_sauna_h + LINE_SPACING

        if time_str and font_time:
            draw.text((text_padding_x, current_y), time_str, font=font_time, fill=TEXT_COLOR)
    except Exception as e:
        print(f"Error drawing text: {e}")

    return image

# --- Image Generation Orchestrator (async) ---

async def generate_timeform_image():
    """Orchestrates weather fetch, font load, screenshot, processing, overlay."""
    # 1. Fetch Weather Data
    weather_data = get_weather_data(MODIFIED_WEATHER_URL)
    text_data = {'temp': '--°C', 'condition': 'Weather unavailable', 'time': None, 'sauna': None}

    # Fetch Sauna Data
    try:
        text_data['sauna'] = get_sauna_status()
    except Exception as e:
        print(f"Error fetching sauna status: {e}")

    if weather_data and 'current' in weather_data:
        try:
            temp_c = weather_data['current']['temp_c']
            text_data['temp'] = f"{temp_c:.0f}°C"
            text_data['condition'] = weather_data['current']['condition']['text']
            if SIMULATE_HOUR is None and 'location' in weather_data and 'localtime' in weather_data['location']:
                 localtime = weather_data['location']['localtime']
                 time_parts = localtime.split(' '); text_data['time'] = time_parts[1] if len(time_parts) == 2 else None
        except KeyError as e: print(f"Warning: Could not extract weather data field: {e}")

    if SIMULATE_HOUR is not None: text_data['time'] = f"{SIMULATE_HOUR:02d}:00"
    elif text_data['time'] is None: print("Warning: Could not determine time string.")

    # 2. Load Fonts
    fonts = load_fonts()
    if not fonts.get('font_temp') or not fonts.get('font_cond'):
        print("Error: Essential fonts could not be loaded. Aborting image generation."); return None

    # 3. Capture Screenshot
    screenshot_bytes = await take_screenshot()
    if not screenshot_bytes: print("Failed to capture screenshot. Aborting image generation."); return None

    # 4. Process Screenshot (Crop, Zoom, Align, Create Canvas)
    background_image, align_artwork_top = process_screenshot(screenshot_bytes)
    if not background_image: print("Failed to process screenshot. Aborting image generation."); return None

    # 5. Add Text Overlay
    final_image = add_text_overlay(background_image, text_data, fonts, align_artwork_top)
    if not final_image: print("Failed to add text overlay. Aborting image generation."); return None

    # Rotate the final image 180 degrees
    final_image = final_image.rotate(180)

    # 6. Save Final Image
    try:
        abs_output_path = os.path.abspath(OUTPUT_FILENAME)
        final_image.save(abs_output_path)
        print(f"Image generated and saved successfully as {abs_output_path}")
        return abs_output_path # Return the full path
    except Exception as e:
        print(f"Error saving final image: {e}")
        return None

def prepare_rotated_image(source_path):
    """Rotates a static image 180 degrees and saves it."""
    try:
        img = Image.open(source_path)
        rotated_img = img.rotate(180)
        output_filename = f"rotated_{os.path.basename(source_path)}"
        abs_path = os.path.abspath(output_filename)
        rotated_img.save(abs_path)
        print(f"Image rotated and saved to: {abs_path}")
        return abs_path
    except Exception as e:
        print(f"Error preparing rotated image: {e}")
        return None

def get_random_easter_egg():
    """Selects a random ENABLED image from the easter eggs directory."""
    if not os.path.exists(EASTER_EGGS_DIR):
        return None


def get_override_image_path():
    """Returns absolute path to override image if set, otherwise None."""
    try:
        if not os.path.exists(EASTER_EGGS_OVERRIDE):
            return None
        with open(EASTER_EGGS_OVERRIDE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        filename = data.get("filename")
        if not filename or not isinstance(filename, str):
            return None
        filename = os.path.basename(filename)
        candidate = os.path.join(EASTER_EGGS_DIR, filename)
        if not os.path.exists(candidate):
            print(f"Warning: override image not found on disk: {candidate}")
            return None
        return os.path.abspath(candidate)
    except Exception as e:
        print(f"Warning: could not read override.json ({e})")
        return None

    enabled_from_manifest = None
    try:
        if os.path.exists(EASTER_EGGS_MANIFEST):
            with open(EASTER_EGGS_MANIFEST, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            images = manifest.get("images", {}) if isinstance(manifest, dict) else {}
            if isinstance(images, dict):
                enabled_from_manifest = [
                    name
                    for name, meta in images.items()
                    if isinstance(meta, dict)
                    and bool(meta.get("enabled", True))
                    and isinstance(name, str)
                ]
    except Exception as e:
        print(f"Warning: could not read manifest.json ({e}). Falling back to filesystem scan.")

    try:
        files = os.listdir(EASTER_EGGS_DIR)
        files = [
            f
            for f in files
            if f != "manifest.json"
            and not f.startswith("rotated_")
            and f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        ]

        if enabled_from_manifest is not None:
            candidates = [f for f in files if f in set(enabled_from_manifest)]
        else:
            candidates = files

        if not candidates:
            return None

        selected_image = random.choice(candidates)
        return os.path.join(EASTER_EGGS_DIR, selected_image)
    except Exception as e:
        print(f"Error selecting random easter egg: {e}")
        return None

def _load_easter_egg_settings():
    """Returns settings dict. If missing/invalid, returns defaults."""
    defaults = {"easter_egg_chance_denominator": 10}
    try:
        if not os.path.exists(EASTER_EGGS_SETTINGS):
            return defaults
        with open(EASTER_EGGS_SETTINGS, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return defaults
        denom = data.get("easter_egg_chance_denominator", defaults["easter_egg_chance_denominator"])
        try:
            denom = int(denom)
        except Exception:
            denom = defaults["easter_egg_chance_denominator"]
        if denom < 0:
            denom = 0
        return {"easter_egg_chance_denominator": denom}
    except Exception as e:
        print(f"Warning: could not read settings.json ({e})")
        return defaults


_ha_cache = {"value": None, "ts": 0.0}


def _ha_explicit_allowed():
    """Returns True if HA explicit boolean is on; False otherwise. Cached for HA_CACHE_TTL_SECONDS."""
    now = time.time()
    if _ha_cache["value"] is not None and (now - _ha_cache["ts"]) < HA_CACHE_TTL_SECONDS:
        return bool(_ha_cache["value"])

    if not HA_BASE_URL or not HA_TOKEN:
        # Not configured -> default to False (safe)
        _ha_cache["value"] = False
        _ha_cache["ts"] = now
        return False

    url = f"{HA_BASE_URL}/api/states/{HA_EXPLICIT_ENTITY}"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
            timeout=HA_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        state = data.get("state")
        allowed = str(state).lower() == "on"
        _ha_cache["value"] = allowed
        _ha_cache["ts"] = now
        return allowed
    except Exception as e:
        print(f"Warning: HA explicit check failed ({e}); treating as OFF")
        # If we had a cached value, keep it; else default False
        if _ha_cache["value"] is None:
            _ha_cache["value"] = False
            _ha_cache["ts"] = now
        return bool(_ha_cache["value"])


def get_sauna_status():
    """
    Fetches the status of the sauna climate entity.
    Returns a dict with 'is_on', 'current_temp', 'set_temp' or None if failed/off.
    """
    if not HA_BASE_URL or not HA_TOKEN:
        return None

    url = f"{HA_BASE_URL}/api/states/{HA_SAUNA_ENTITY}"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
            timeout=HA_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        state = data.get("state")
        attributes = data.get("attributes", {})
        print(f"Sauna state: {state}")
        print(f"Sauna attributes: {attributes}")
        is_on = state == "heat_cool"
        if is_on:
             return {
                 "is_on": True,
                 "current_temp": attributes.get("current_temperature"),
                 "set_temp": attributes.get("temperature")
             }
        return None

    except Exception as e:
        print(f"Warning: HA sauna check failed ({e})")
        return None


def _get_enabled_easter_egg_candidates():
    """Returns (files_on_disk, enabled_set, explicit_set, priority_map)."""
    files = []
    try:
        files = os.listdir(EASTER_EGGS_DIR)
        files = [
            f
            for f in files
            if f != "manifest.json"
            and f != "override.json"
            and f != "settings.json"
            and not f.startswith("rotated_")
            and f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
        ]
    except Exception:
        files = []

    enabled_set = None
    explicit_set = set()
    priority_map = {}
    try:
        if os.path.exists(EASTER_EGGS_MANIFEST):
            with open(EASTER_EGGS_MANIFEST, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            images = manifest.get("images", {}) if isinstance(manifest, dict) else {}
            if isinstance(images, dict):
                enabled = []
                for name, meta in images.items():
                    if not isinstance(name, str) or not isinstance(meta, dict):
                        continue
                    if bool(meta.get("enabled", True)):
                        enabled.append(name)
                    if bool(meta.get("explicit", False)):
                        explicit_set.add(name)
                    # priority 1..10 (higher = more likely)
                    prio = meta.get("priority", 5)
                    try:
                        prio_i = int(prio)
                    except Exception:
                        prio_i = 5
                    if prio_i < 1:
                        prio_i = 1
                    if prio_i > 10:
                        prio_i = 10
                    priority_map[name] = prio_i
                enabled_set = set(enabled)
    except Exception as e:
        print(f"Warning: could not read manifest.json for explicit filtering ({e})")

    return files, enabled_set, explicit_set, priority_map


def get_random_easter_egg_filtered():
    """
    Picks a random enabled image from eastereggs/, filtering explicit images
    if Home Assistant explicit boolean is OFF.
    """
    if not os.path.exists(EASTER_EGGS_DIR):
        return None

    files, enabled_set, explicit_set, priority_map = _get_enabled_easter_egg_candidates()
    if enabled_set is not None:
        candidates = [f for f in files if f in enabled_set]
    else:
        candidates = files

    if not candidates:
        return None

    allow_explicit = _ha_explicit_allowed()
    if not allow_explicit:
        candidates = [f for f in candidates if f not in explicit_set]

    if not candidates:
        return None

    weights = [max(1, int(priority_map.get(f, 5))) for f in candidates]
    selected_image = random.choices(candidates, weights=weights, k=1)[0]
    return os.path.join(EASTER_EGGS_DIR, selected_image)


def _write_live_preview(uploaded_image_path, meta):
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

# --- Samsung TV Interaction (Synchronous) ---

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

# --- Main Loop (Synchronous) ---

def main_loop(tv_ip, interval_minutes):
    """Runs the image generation and TV update periodically."""
    logging.basicConfig(level=logging.INFO)
    print(f"Starting main loop. TV IP: {tv_ip}, Update Interval: {interval_minutes} minutes.")
    
    # Check reachability before initial connection
    if not is_tv_reachable(tv_ip):
         print(f"TV at {tv_ip} is initially unreachable. It will be checked in the loop.")
         tv = False
    else:
        try:
             tv = connect_to_tv(tv_ip)
        except Exception as e:
            print(f"Initial connection failed: {e}")
            tv = False

    iteration = 1
    while True:
        # Check if TV is reachable
        if not is_tv_reachable(tv_ip):
            print(f"\n===== TV at {tv_ip} is unreachable (Ping failed). =====")
            print(f"Sleeping for 10 seconds before retrying...")
            time.sleep(10)
            continue

        if iteration % 10 == 0 or tv is False:
            print("Reconnecting to TV...")
            try:
                tv = connect_to_tv(tv_ip)
            except Exception as e:
                print(f"Connection failed even after successful ping: {e}")
                tv = False
                time.sleep(10)
                continue

        print(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} - Running Update Cycle {iteration} ====")
        try:
            if tv is False:
                print("Failed to connect to TV. Skipping update.")
                continue

            # Determine which image to show
            override_path = get_override_image_path()
            if override_path:
                print(f"Override active: {override_path}")
                override_filename = os.path.basename(override_path)
                preserve = _preserved_content_ids()
                cached_id = _get_cached_content_id(override_filename)
                # Always generate a rotated preview image for the web UI
                rotated_for_preview = prepare_rotated_image(override_path)
                if cached_id:
                    print(f"Reusing cached TV content_id for override: {cached_id}")
                    ok = select_tv_art(tv, cached_id, preserve_ids=preserve)
                    if ok and rotated_for_preview:
                        _write_live_preview(rotated_for_preview, {"type": "override", "filename": override_filename})
                    iteration += 1
                    # Sleep until next cycle
                    current_time = time.time()
                    seconds_past_minute = current_time % 60
                    sleep_seconds = (interval_minutes * 60) - seconds_past_minute
                    if sleep_seconds == 0:
                        sleep_seconds = (interval_minutes * 60) - 1
                    print(f"===== Cycle finished. Sleeping for {sleep_seconds:.2f} seconds until next minute... ====")
                    time.sleep(sleep_seconds)
                    continue
                else:
                    # First time: upload once and cache content_id
                    image_path = rotated_for_preview
                    live_meta = {"type": "override", "filename": override_filename}
            else:
                image_path = None

            # Easter egg frequency: 1 in N chance (configured via eastereggs/settings.json)
            settings = _load_easter_egg_settings()
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
                     preserve = _preserved_content_ids()
                     cached_id = _get_cached_content_id(egg_filename)
                     rotated_for_preview = prepare_rotated_image(egg_path)
                     if cached_id:
                         print(f"Reusing cached TV content_id for easteregg: {cached_id}")
                         ok = select_tv_art(tv, cached_id, preserve_ids=preserve)
                         if ok and rotated_for_preview:
                             _write_live_preview(rotated_for_preview, {"type": "easteregg", "filename": egg_filename})
                         iteration += 1
                         current_time = time.time()
                         seconds_past_minute = current_time % 60
                         sleep_seconds = (interval_minutes * 60) - seconds_past_minute
                         if sleep_seconds == 0:
                             sleep_seconds = (interval_minutes * 60) - 1
                         print(f"===== Cycle finished. Sleeping for {sleep_seconds:.2f} seconds until next minute... ====")
                         time.sleep(sleep_seconds)
                         continue
                     else:
                         image_path = rotated_for_preview
                         live_meta = {"type": "easteregg", "filename": egg_filename}
                else:
                     print("No easter eggs found. Falling back to Timeform.")

            # If not easter egg or easter egg failed, generate Timeform
            if not image_path:
                # Run the async image generation
                image_path = asyncio.run(generate_timeform_image())
                live_meta = {"type": "timeform", "filename": os.path.basename(image_path) if image_path else None}

            if image_path:
                # Run the synchronous TV update
                preserve = _preserved_content_ids()
                new_id = update_tv_art(tv, image_path, preserve_ids=preserve)
                if new_id:
                    # Cache content_id only for eastereggs/override (files under eastereggs/)
                    try:
                        if live_meta.get("type") in ("easteregg", "override") and live_meta.get("filename"):
                            _set_cached_content_id(live_meta["filename"], new_id)
                    except Exception:
                        pass
                    _write_live_preview(image_path, live_meta if "live_meta" in locals() else {"type": None, "filename": None})
            else:
                print("Image generation/selection failed, skipping TV update.")

        except Exception as e:
            print(f"Error in main loop cycle: {e}")

        # Calculate seconds until the next minute
        current_time = time.time()
        seconds_past_minute = current_time % 60
        sleep_seconds = (interval_minutes * 60) - seconds_past_minute
        if sleep_seconds == 0: # Avoid 0 sleep if exactly on the minute
            sleep_seconds = (interval_minutes * 60) - 1

        print(f"===== Cycle finished. Sleeping for {sleep_seconds:.2f} seconds until next minute... ====")
        time.sleep(sleep_seconds)
        iteration += 1

if __name__ == "__main__":
    # Ensure TV_IP is set correctly before running!
    if TV_IP == "192.168.1.100":
       print("\n!!! WARNING: TV_IP is set to the default placeholder.")
       print("!!! Please edit the script and set TV_IP to your Samsung Frame TV's actual IP address.\n")
       # exit(1) # Optional: Uncomment to prevent running with placeholder
    # update_tv_art(TV_IP, '/Users/sjoerdbolten/Documents/Projects/tijdvorm/py/timeform_art.png')
    main_loop(TV_IP, UPDATE_INTERVAL_MINUTES) 
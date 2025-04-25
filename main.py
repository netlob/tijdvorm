import asyncio
from playwright.async_api import async_playwright
from PIL import Image, ImageDraw, ImageFont
import io
import os
import time
import requests
import logging

from samsungtvws import SamsungTVWS

# --- Samsung TV Config ---
TV_IP = "10.0.1.111" # !!! REPLACE WITH YOUR TV's IP ADDRESS !!!
UPDATE_INTERVAL_MINUTES = 1
DELETE_OLD_ART = False # turn on to always delete all manually uploaded art
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
    draw = ImageDraw.Draw(image)
    
    temp_str = text_data.get('temp', '--°C')
    cond_str = text_data.get('condition', 'Unknown')
    time_str = time.strftime("%H:%M")

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
    text_data = {'temp': '--°C', 'condition': 'Weather unavailable', 'time': None}
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

    # 6. Save Final Image
    try:
        abs_output_path = os.path.abspath(OUTPUT_FILENAME)
        final_image.save(abs_output_path)
        print(f"Image generated and saved successfully as {abs_output_path}")
        return abs_output_path # Return the full path
    except Exception as e:
        print(f"Error saving final image: {e}")
        return None

# --- Samsung TV Interaction (Synchronous) ---

def update_tv_art(tv_ip, image_path):
    """Connects to TV, uploads image, cleans old, selects new."""
    print(f"--- Starting TV Update for {tv_ip} --- ")
    try:
        print("Connecting to TV...")
        tv = SamsungTVWS(tv_ip)
        # Optional: Check connection state if library provides it
        print("Connected.")

        # 1. Upload new art
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

        # 2. Get existing user art
        print("Getting available art list...")
        available_art = tv.art().available()
        # if isinstance(available_art, str):
        #     available_art = json.loads(available_art)
        if not available_art:
            print("Warning: Could not get available art list or list is empty.")
            user_art_ids = []
        else:
            user_art_ids = [art['content_id'] for art in available_art if art['content_id'].startswith('MY_')]
            print(f"Found {len(user_art_ids)} existing user art pieces.")


        # 3. Select the new art
        print(f"Selecting new image: {new_content_id}")
        tv.art().select_image(new_content_id, show=True)
        print("Selection command sent.")

        # 3. Delete old art (except the new one)
        ids_to_delete = [art_id for art_id in user_art_ids if art_id != new_content_id]
        if ids_to_delete and DELETE_OLD_ART:
            print(f"Deleting {len(ids_to_delete)} old user art pieces: {ids_to_delete}")
            delete_result = tv.art().delete_list(ids_to_delete)
            # Check delete_result if needed (docs don't specify return value)
            print("Deletion command sent.")
        else:
            print("No old user art pieces to delete.")

        # 5. Ensure Art Mode is On
        try:
            print("Ensuring Art Mode is ON...")
            tv.art().set_artmode(True)
            print("Set Art Mode command sent.")
        except Exception as e_artmode:
            print(f"Warning: Could not set Art Mode (may already be on or TV off): {e_artmode}")

        print("--- TV Update Finished ---")
        return True

    except Exception as e:
        print(f"Error during TV interaction: {e}")
        print("--- TV Update Failed ---")
        return False

# --- Main Loop (Synchronous) ---

def main_loop(tv_ip, interval_minutes):
    """Runs the image generation and TV update periodically."""
    logging.basicConfig(level=logging.INFO)
    print(f"Starting main loop. TV IP: {tv_ip}, Update Interval: {interval_minutes} minutes.")
    while True:
        print(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} - Running Update Cycle ====")
        try:
            # Run the async image generation
            image_path = asyncio.run(generate_timeform_image())

            if image_path:
                # Run the synchronous TV update
                update_tv_art(tv_ip, image_path)
            else:
                print("Image generation failed, skipping TV update.")

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

if __name__ == "__main__":
    # Ensure TV_IP is set correctly before running!
    if TV_IP == "192.168.1.100":
       print("\n!!! WARNING: TV_IP is set to the default placeholder.")
       print("!!! Please edit the script and set TV_IP to your Samsung Frame TV's actual IP address.\n")
       # exit(1) # Optional: Uncomment to prevent running with placeholder
    # update_tv_art(TV_IP, '/Users/sjoerdbolten/Documents/Projects/tijdvorm/py/timeform_art.png')
    main_loop(TV_IP, UPDATE_INTERVAL_MINUTES) 
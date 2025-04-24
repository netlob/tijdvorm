import asyncio
from playwright.async_api import async_playwright
from PIL import Image, ImageOps, ImageDraw, ImageFont
import io
import os
import time
import re
import requests

URL = "https://timeforms.app"
# Selector for the main artwork container (used to wait for page readiness)
ARTWORK_FRAME_SELECTOR = "#root > div.w-full.min-h-screen.flex.items-center.justify-center.p-8.transition-colors.duration-1000.relative > div.absolute.top-1\\/2.left-1\\/2.-translate-y-1\\/2.-translate-x-1\\/2.w-full.flex.justify-center.items-center > div > div"
# Selector for the time simulation slider track
SLIDER_TRACK_SELECTOR = 'span.relative.flex.touch-none.select-none.items-center.w-full.slider-custom'
# TIME_DISPLAY_SPAN_SELECTOR = 'span:has-text("Time Display")' # User commented out

OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FILENAME = "timeform_art_v18.png" # Changed filename
PAGE_LOAD_TIMEOUT = 90000
SELECTOR_TIMEOUT = 60000

# --- Configuration ---
# Set hour to simulate (0-23), or None to use current time
SIMULATE_HOUR = None # User updated

# Crop values
CROP_LEFT = 110
CROP_RIGHT_MARGIN = 110
CROP_TOP = 192
CROP_BOTTOM_MARGIN = 192

# Background color for the final canvas - Will be set dynamically
# BG_COLOR = (248, 248, 249)

# Zoom factor
ZOOM_FACTOR = 1.15

# Color comparison tolerance (sum of absolute differences in R, G, B)
COLOR_TOLERANCE = 30

# --- Network Interception ---
TARGET_WEATHER_URL = "https://api.weatherapi.com/v1/current.json?key=8cd71ded6ce646e888600951251504&q=Brooklyn,NY"
MODIFIED_WEATHER_URL = "https://api.weatherapi.com/v1/current.json?key=8cd71ded6ce646e888600951251504&q=Amsterdam,NL"
# --- End Network Interception ---

# CSS - User reverted some changes, keeping slider hidden
# Also keep hiding bottom-left text as toggle click is removed
HIDE_CSS = """
  /* Main UI elements outside the frame */
  .fixed.top-8.left-8.text-2xl,
  .fixed.bottom-8.left-8.text-xs,
  .fixed.left-8.top-1\\/2.-translate-y-1\\/2, /* Escape slashes for CSS (double backslash for Python string) */
  .fixed.left-8.z-50, /* Includes the parent container of the panel */
  .fixed.bottom-0.left-0.right-0.w-full.z-50,
  /* Text block inside the artwork frame */
   .absolute.bottom-6.left-6.text-gray-600.z-30,
  /* Always hide slider controls */
  span.relative.flex.touch-none.select-none.items-center.w-full.slider-custom,
  button:has(svg.lucide-play),
  button:has(svg.lucide-rotate-ccw) {
    display: none !important;
  }
  /* Optional: Ensure the main container takes full space if needed */
  /* body, #root { overflow: hidden; } */
"""

# Helper function for color difference
def color_diff(color1, color2):
    if not color1 or not color2 or len(color1) < 3 or len(color2) < 3:
        return float('inf') # Max difference if colors are invalid
    return sum(abs(c1 - c2) for c1, c2 in zip(color1[:3], color2[:3]))

# Function to get weather data
def get_weather_data(url):
    print(f"Fetching weather data from: {url}")
    try:
        response = requests.get(url, timeout=10) # Add timeout
        response.raise_for_status() # Raise error for bad responses (4xx or 5xx)
        data = response.json()
        print("Weather data fetched successfully.")
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching weather data: {e}")
        return None

# --- Text Overlay Config ---
FONT_DIR = "fonts"
# Use Light for regular text
FONT_NAME_LIGHT = "Inter-Light.ttf"
FONT_SAVE_PATH_LIGHT = os.path.join(FONT_DIR, FONT_NAME_LIGHT)
# Use Bold for temperature
FONT_NAME_BOLD = "Inter-Bold.ttf"
FONT_SAVE_PATH_BOLD = os.path.join(FONT_DIR, FONT_NAME_BOLD)

# System font paths (fallback)
SYSTEM_FONT_PATHS_TO_TRY = [
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
]
TEMP_FONT_SIZE = 63
COND_FONT_SIZE = 47
TIME_FONT_SIZE = 39
TEXT_COLOR = (75, 85, 99)
TEXT_PADDING = 60
LINE_SPACING = 26

# Simplified function to load font
def load_font(local_font_path, fallback_paths, size):
    abs_local_path = os.path.abspath(local_font_path)
    # Try loading local font first
    try:
        print(f"Attempting to load local font: {abs_local_path}")
        return ImageFont.truetype(abs_local_path, size)
    except IOError as e:
        print(f"Error loading local font '{abs_local_path}': {e}. Trying system fonts.")

    # Fallback to system fonts
    for path in fallback_paths:
        try:
            return ImageFont.truetype(path, size)
        except IOError:
            continue

    print(f"Warning: None of the specified system fonts found ({fallback_paths}). Using default Pillow font.")
    # Fallback to Pillow default
    try:
        return ImageFont.load_default()
    except IOError:
        print("Error: Could not load even the default Pillow font.")
        return None

async def main():
    # --- Fetch Weather Data (before launching browser) ---
    weather_data = get_weather_data(MODIFIED_WEATHER_URL)
    temp_str = "--°C" # Default to Celsius
    cond_str = "Weather unavailable"
    time_str = None # Will be determined later

    if weather_data and 'current' in weather_data:
        try:
            # Fetch Celsius temp
            temp_c = weather_data['current']['temp_c']
            temp_str = f"{temp_c:.0f}°C" # Format as integer + °C
            cond_str = weather_data['current']['condition']['text']
            if SIMULATE_HOUR is None and 'location' in weather_data and 'localtime' in weather_data['location']:
                 # Extract HH:MM from "YYYY-MM-DD HH:MM"
                 localtime = weather_data['location']['localtime']
                 time_parts = localtime.split(' ')
                 if len(time_parts) == 2:
                     time_str = time_parts[1]
                 print(f"Using actual local time from API: {time_str}")

        except KeyError as e:
            print(f"Warning: Could not extract weather data field: {e}")

    # Determine time string based on simulation or API data
    if SIMULATE_HOUR is not None:
        time_str = f"{SIMULATE_HOUR:02d}:00"
        print(f"Using simulated time: {time_str}")
    elif time_str is None:
        print("Warning: Could not determine time string.")
        # Keep time_str as None, it won't be drawn

    # --- Load Fonts (Using simplified function) ---
    print("Loading fonts...")
    font_temp_bold = load_font(FONT_SAVE_PATH_BOLD, SYSTEM_FONT_PATHS_TO_TRY, TEMP_FONT_SIZE)
    font_cond = load_font(FONT_SAVE_PATH_LIGHT, SYSTEM_FONT_PATHS_TO_TRY, COND_FONT_SIZE)
    font_time = load_font(FONT_SAVE_PATH_LIGHT, SYSTEM_FONT_PATHS_TO_TRY, TIME_FONT_SIZE)

    # --- Launch Browser and Navigate ---
    print("Launching browser...")
    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch()
            print("Chromium launched.")
        except Exception as e:
            print(f"Failed to launch Chromium: {e}. Trying Firefox...")
            try:
                 browser = await p.firefox.launch()
                 print("Firefox launched.")
            except Exception as e2:
                 print(f"Failed to launch Firefox: {e2}")
                 print("Please ensure Playwright browsers are installed ('playwright install')")
                 return
        if not browser:
            return

        page = await browser.new_page(viewport={"width": OUTPUT_WIDTH, "height": OUTPUT_HEIGHT})

        # --- Set up request routing ---
        async def handle_route(route):
            # No need to print every interception, only the modification
            # print(f"Intercepted: {route.request.url}") 
            if route.request.url == TARGET_WEATHER_URL:
                print(f"Intercepted weather API call. Modifying location to Amsterdam, NL.")
                # print(f"  Original: {route.request.url}")
                # print(f"  Modified: {MODIFIED_WEATHER_URL}")
                await route.continue_(url=MODIFIED_WEATHER_URL)
            else:
                # Let other requests pass through unmodified
                await route.continue_()

        # Intercept the specific URL pattern
        await page.route(TARGET_WEATHER_URL, handle_route)
        print(f"Set up route handler for weather API.")
        # --- End request routing setup ---

        print(f"Navigating to {URL}...")
        try:
            # Wait for network idle after routing might be more reliable
            await page.goto(URL, timeout=PAGE_LOAD_TIMEOUT, wait_until='networkidle')
            print("Page navigation complete (Network Idle).")
        except Exception as e:
            print(f"Error navigating to page or timeout exceeded: {e}")
            await browser.close()
            return

        # print("Waiting briefly for initial script execution...") # Less needed after networkidle
        # await asyncio.sleep(2)

        # User commented out Time Display click
        # # --- Click Time Display Toggle ---
        # ...

        # --- Time Simulation ---
        if SIMULATE_HOUR is not None and 0 <= SIMULATE_HOUR <= 23:
            print(f"Simulating time: {SIMULATE_HOUR}:00")
            try:
                slider_track = page.locator(SLIDER_TRACK_SELECTOR)
                await slider_track.wait_for(state="visible", timeout=SELECTOR_TIMEOUT)
                bbox = await slider_track.bounding_box()
                if bbox:
                    click_x = bbox['x'] + (SIMULATE_HOUR / 23) * bbox['width']
                    click_y = bbox['y'] + bbox['height'] / 2
                    print(f"Clicking slider track at ({click_x:.2f}, {click_y:.2f})")
                    await page.mouse.click(click_x, click_y)
                    print("Waiting 1 second for time simulation update...")
                    await asyncio.sleep(1)
                else:
                    print("Error: Could not get slider track bounding box.")
            except Exception as e:
                print(f"Error interacting with slider: {e}")
        else:
            print("Using current time (simulation disabled or invalid hour).")

        print("Injecting CSS to hide UI elements...")
        # Use the static HIDE_CSS
        try:
            await page.add_style_tag(content=HIDE_CSS)
            print("CSS injected.")
        except Exception as e:
            print(f"Error injecting CSS: {e}")

        print(f"Waiting for artwork frame selector '{ARTWORK_FRAME_SELECTOR}'...")
        # ... (Wait for artwork frame) ...
        try:
            # Add a slightly longer wait here AFTER potential time simulation/CSS injection
            await page.locator(ARTWORK_FRAME_SELECTOR).wait_for(state='visible', timeout=SELECTOR_TIMEOUT)
            print("Artwork frame found. Waiting a bit longer for rendering...")
            await asyncio.sleep(2) # Wait for rendering after finding frame
        except Exception as e:
            print(f"Error finding artwork frame selector or timeout exceeded: {e}")
            await browser.close()
            return

        print("Taking screenshot of the page...")
        # ... (Take screenshot) ...
        try:
            screenshot_bytes = await page.screenshot()
            print("Screenshot taken.")
        except Exception as e:
            print(f"Error taking screenshot: {e}")
            await browser.close()
            return

        await browser.close()
        print("Browser closed.")

        print("Processing image...")
        img = Image.open(io.BytesIO(screenshot_bytes))
        img_w, img_h = img.size
        print(f"Original page screenshot size: {img_w}x{img_h}")
        crop_box = (CROP_LEFT, CROP_TOP, img_w - CROP_RIGHT_MARGIN, img_h - CROP_BOTTOM_MARGIN)
        print(f"Calculated crop box: {crop_box}")
        # ... (Crop validation)
        if crop_box[0] >= crop_box[2] or crop_box[1] >= crop_box[3]:
            print(f"Error: Invalid crop dimensions calculated. Left={crop_box[0]}, Top={crop_box[1]}, Right={crop_box[2]}, Bottom={crop_box[3]}")
            return
        cropped_img = img.crop(crop_box)
        cropped_w, cropped_h = cropped_img.size
        print(f"Cropped image size: {cropped_w}x{cropped_h}")

        top_left_color = (255, 255, 255)
        top_center_color = (255, 255, 255)
        dynamic_bg_color = top_left_color
        try:
            top_left_color_raw = cropped_img.getpixel((0, 0))
            top_left_color = top_left_color_raw[:3] if len(top_left_color_raw) == 4 else top_left_color_raw
            dynamic_bg_color = top_left_color
            print(f"Using dynamic background color from top-left pixel: {dynamic_bg_color}")
            center_x = cropped_w // 2
            top_center_color_raw = cropped_img.getpixel((center_x, 0))
            top_center_color = top_center_color_raw[:3] if len(top_center_color_raw) == 4 else top_center_color_raw
            print(f"Top-center pixel color: {top_center_color}")
        except Exception as e:
            print(f"Warning: Could not get pixel colors: {e}. Using fallback white background and default alignment.")

        scaled_w = int(cropped_w * ZOOM_FACTOR)
        scaled_h = int(cropped_h * ZOOM_FACTOR)
        print(f"Scaling cropped image by {ZOOM_FACTOR}x to: {scaled_w}x{scaled_h}")
        scaled_img = cropped_img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

        background = Image.new('RGB', (OUTPUT_WIDTH, OUTPUT_HEIGHT), dynamic_bg_color)
        print(f"Created background canvas: {OUTPUT_WIDTH}x{OUTPUT_HEIGHT} with color {dynamic_bg_color}")

        offset_x = (OUTPUT_WIDTH - scaled_w) // 2
        diff = color_diff(top_left_color, top_center_color)
        print(f"Color difference (sum of abs RGB diff): {diff}")

        if diff <= COLOR_TOLERANCE:
            print(f"Color difference ({diff}) <= tolerance ({COLOR_TOLERANCE}). Aligning to bottom.")
            offset_y = OUTPUT_HEIGHT - scaled_h # Align bottom
        else:
            print(f"Color difference ({diff}) > tolerance ({COLOR_TOLERANCE}). Aligning to top.")
            offset_y = 0 # Align top

        print(f"Pasting scaled image onto background at offset: ({offset_x}, {offset_y})")
        background.paste(scaled_img, (offset_x, offset_y))

        # --- Draw Text Overlay ---
        draw = ImageDraw.Draw(background)
        text_block_height = 0
        bbox_temp_h, bbox_cond_h, bbox_time_h = 0, 0, 0

        # Calculate text block height using potentially different fonts
        if font_temp_bold:
            try: bbox_temp_h = draw.textbbox((0, 0), temp_str, font=font_temp_bold)[3] - draw.textbbox((0, 0), temp_str, font=font_temp_bold)[1]
            except Exception: bbox_temp_h = TEMP_FONT_SIZE # Estimate
        if font_cond:
            try: bbox_cond_h = draw.textbbox((0, 0), cond_str, font=font_cond)[3] - draw.textbbox((0, 0), cond_str, font=font_cond)[1]
            except Exception: bbox_cond_h = COND_FONT_SIZE # Estimate
        if time_str and font_time:
            try: bbox_time_h = draw.textbbox((0, 0), time_str, font=font_time)[3] - draw.textbbox((0, 0), time_str, font=font_time)[1]
            except Exception: bbox_time_h = TIME_FONT_SIZE # Estimate

        text_block_height = bbox_temp_h + LINE_SPACING + bbox_cond_h
        if time_str:
             text_block_height += LINE_SPACING + bbox_time_h

        # Determine Y start position (using user's padding)
        if offset_y == 0:
            # Artwork at top, text at bottom-left
            text_y = OUTPUT_HEIGHT - text_block_height - (TEXT_PADDING * 1.5)
            print(f"Drawing text at bottom-left (y={text_y})")
        else:
            # Artwork at bottom, text at top-left
            text_y = TEXT_PADDING * 1.5
            print(f"Drawing text at top-left (y={text_y})")

        current_y = text_y
        # Draw Temperature (Bold)
        if font_temp_bold:
            try:
                draw.text((TEXT_PADDING, current_y), temp_str, font=font_temp_bold, fill=TEXT_COLOR)
                current_y += bbox_temp_h + (LINE_SPACING * 1.3)
            except Exception as e: print(f"Error drawing temp text: {e}")
        # Draw Condition (Light)
        if font_cond:
             try:
                draw.text((TEXT_PADDING, current_y), cond_str, font=font_cond, fill=TEXT_COLOR)
                current_y += bbox_cond_h + LINE_SPACING
             except Exception as e: print(f"Error drawing condition text: {e}")
        # Draw Time (Light)
        if time_str and font_time:
            try:
                draw.text((TEXT_PADDING, current_y), time_str, font=font_time, fill=TEXT_COLOR)
            except Exception as e: print(f"Error drawing time text: {e}")
        # --- End Draw Text Overlay ---

        background.save(OUTPUT_FILENAME)
        print(f"Image saved as {OUTPUT_FILENAME} ({OUTPUT_WIDTH}x{OUTPUT_HEIGHT})")

if __name__ == "__main__":
    asyncio.run(main()) 
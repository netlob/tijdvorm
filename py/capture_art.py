import asyncio
from playwright.async_api import async_playwright
from PIL import Image, ImageOps
import io
import os
import time

URL = "https://timeforms.app"
# Selector for the main artwork container (used to wait for page readiness)
ARTWORK_FRAME_SELECTOR = "#root > div.w-full.min-h-screen.flex.items-center.justify-center.p-8.transition-colors.duration-1000.relative > div.absolute.top-1\\/2.left-1\\/2.-translate-y-1\\/2.-translate-x-1\\/2.w-full.flex.justify-center.items-center > div > div"
# Selector for the time simulation slider track
SLIDER_TRACK_SELECTOR = 'span.relative.flex.touch-none.select-none.items-center.w-full.slider-custom'
TIME_DISPLAY_SPAN_SELECTOR = 'span:has-text("Time Display")'

OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FILENAME = "timeform_art_v11.png" # Changed filename
PAGE_LOAD_TIMEOUT = 90000
SELECTOR_TIMEOUT = 60000

# --- Configuration ---
# Set hour to simulate (0-23), or None to use current time
SIMULATE_HOUR = 14 # Example: Simulate 2 PM

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

# CSS - Always hide slider controls
HIDE_CSS = """
  /* Main UI elements outside the frame */
  .fixed.top-8.left-8.text-2xl,
  .fixed.bottom-8.left-8.text-xs,
  .fixed.left-8.top-1\\/2.-translate-y-1\\/2, /* Escape slashes for CSS (double backslash for Python string) */
  .fixed.left-8.z-50, /* Includes the parent container of the panel */
  .fixed.bottom-0.left-0.right-0.w-full.z-50,
  /* Text block inside the artwork frame */
  .absolute.bottom-6.left-6.text-gray-600.z-30 {
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

async def main():
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

        print(f"Navigating to {URL}...")
        try:
            await page.goto(URL, timeout=PAGE_LOAD_TIMEOUT, wait_until='domcontentloaded')
            print("Page navigation complete (DOM loaded).")
        except Exception as e:
            print(f"Error navigating to page or timeout exceeded: {e}")
            await browser.close()
            return

        print("Waiting briefly for initial script execution...")
        await asyncio.sleep(2) # Slightly longer wait for dynamic elements like slider

        # # --- Click Time Display Toggle --- 
        # try:
        #     print("Attempting to click 'Time Display' toggle...")
        #     # Find the span, then find its parent div, then find the button within that div
        #     time_display_span = page.locator(TIME_DISPLAY_SPAN_SELECTOR)
        #     # Using XPath to find the button sibling reliably
        #     toggle_button = time_display_span.locator("xpath=./following-sibling::button")
        #     await toggle_button.wait_for(state="visible", timeout=SELECTOR_TIMEOUT)
        #     await toggle_button.click()
        #     print("'Time Display' toggle clicked.")
        #     await asyncio.sleep(0.5) # Brief pause after click
        # except Exception as e:
        #     print(f"Warning: Could not find or click 'Time Display' toggle: {e}")
        # # --- End Click Time Display Toggle ---

        # --- Time Simulation --- 
        if SIMULATE_HOUR is not None and 0 <= SIMULATE_HOUR <= 23:
            print(f"Simulating time: {SIMULATE_HOUR}:00")
            try:
                slider_track = page.locator(SLIDER_TRACK_SELECTOR)
                await slider_track.wait_for(state="visible", timeout=SELECTOR_TIMEOUT)
                bbox = await slider_track.bounding_box()

                if bbox:
                    # Calculate click position
                    click_x = bbox['x'] + (SIMULATE_HOUR / 23) * bbox['width']
                    click_y = bbox['y'] + bbox['height'] / 2
                    print(f"Clicking slider track at ({click_x:.2f}, {click_y:.2f})")
                    await page.mouse.click(click_x, click_y)
                    print("Waiting 1 second for time simulation update...")
                    await asyncio.sleep(1) # Wait for visual update
                else:
                    print("Error: Could not get slider track bounding box.")

            except Exception as e:
                print(f"Error interacting with slider: {e}")
                # Continue anyway, might just use current time
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
        # We still wait for the main artwork frame to ensure page is generally ready
        try:
            await page.locator(ARTWORK_FRAME_SELECTOR).wait_for(state='visible', timeout=SELECTOR_TIMEOUT)
            print("Artwork frame found.")
        except Exception as e:
            print(f"Error finding artwork frame selector or timeout exceeded: {e}")
            await browser.close()
            return

        # User removed wait and added scroll - keeping scroll commented for now
        # await asyncio.sleep(10)
        # await page.evaluate("window.scrollBy(0, 1000);")

        print("Taking screenshot of the page...")
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

        crop_box = (
            CROP_LEFT,
            CROP_TOP,
            img_w - CROP_RIGHT_MARGIN,
            img_h - CROP_BOTTOM_MARGIN
        )
        print(f"Calculated crop box: {crop_box}")

        # Ensure crop box is valid
        if crop_box[0] >= crop_box[2] or crop_box[1] >= crop_box[3]:
            print(f"Error: Invalid crop dimensions calculated. Left={crop_box[0]}, Top={crop_box[1]}, Right={crop_box[2]}, Bottom={crop_box[3]}")
            return

        cropped_img = img.crop(crop_box)
        cropped_w, cropped_h = cropped_img.size
        print(f"Cropped image size: {cropped_w}x{cropped_h}")

        # --- Get Pixel Colors for Alignment & Background ---
        top_left_color = (255, 255, 255) # Default fallback
        top_center_color = (255, 255, 255) # Default fallback
        dynamic_bg_color = top_left_color # Use top-left for background

        try:
            # Get top-left pixel (and use for background)
            top_left_color_raw = cropped_img.getpixel((0, 0))
            top_left_color = top_left_color_raw[:3] if len(top_left_color_raw) == 4 else top_left_color_raw
            dynamic_bg_color = top_left_color # Update background color
            print(f"Using dynamic background color from top-left pixel: {dynamic_bg_color}")

            # Get top-center pixel
            center_x = cropped_w // 2
            top_center_color_raw = cropped_img.getpixel((center_x, 0))
            top_center_color = top_center_color_raw[:3] if len(top_center_color_raw) == 4 else top_center_color_raw
            print(f"Top-center pixel color: {top_center_color}")

        except Exception as e:
            print(f"Warning: Could not get pixel colors: {e}. Using fallback white background and default alignment.")
        # --- End Pixel Color Logic ---

        # --- Zoom --- 
        scaled_w = int(cropped_w * ZOOM_FACTOR)
        scaled_h = int(cropped_h * ZOOM_FACTOR)
        print(f"Scaling cropped image by {ZOOM_FACTOR}x to: {scaled_w}x{scaled_h}")
        scaled_img = cropped_img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

        # Create background canvas using dynamic color
        background = Image.new('RGB', (OUTPUT_WIDTH, OUTPUT_HEIGHT), dynamic_bg_color)
        print(f"Created background canvas: {OUTPUT_WIDTH}x{OUTPUT_HEIGHT} with color {dynamic_bg_color}")

        # --- Conditional Alignment with Tolerance --- 
        offset_x = (OUTPUT_WIDTH - scaled_w) // 2
        diff = color_diff(top_left_color, top_center_color)
        print(f"Color difference (sum of abs RGB diff): {diff}")

        if diff <= COLOR_TOLERANCE:
            print(f"Color difference ({diff}) <= tolerance ({COLOR_TOLERANCE}). Aligning to bottom.")
            offset_y = OUTPUT_HEIGHT - scaled_h # Align bottom
        else:
            print(f"Color difference ({diff}) > tolerance ({COLOR_TOLERANCE}). Aligning to top.")
            offset_y = 0 # Align top
        # --- End Conditional Alignment ---

        print(f"Pasting scaled image onto background at offset: ({offset_x}, {offset_y})")
        background.paste(scaled_img, (offset_x, offset_y))

        background.save(OUTPUT_FILENAME)
        print(f"Image saved as {OUTPUT_FILENAME} ({OUTPUT_WIDTH}x{OUTPUT_HEIGHT})")

if __name__ == "__main__":
    asyncio.run(main()) 
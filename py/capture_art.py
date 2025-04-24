import asyncio
from playwright.async_api import async_playwright
from PIL import Image, ImageOps
import io
import os
import time

URL = "https://timeforms.app"
# Target the inner div containing the artwork, escaping special characters
# SELECTOR = "div.absolute.inset-\[24px\].overflow-hidden"
SELECTOR = "#root > div.w-full.min-h-screen.flex.items-center.justify-center.p-8.transition-colors.duration-1000.relative > div.absolute.top-1\\/2.left-1\\/2.-translate-y-1\\/2.-translate-x-1\\/2.w-full.flex.justify-center.items-center > div > div"
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FILENAME = "timeform_art_v6.png" # Changed filename
PAGE_LOAD_TIMEOUT = 90000  # 90 seconds
SELECTOR_TIMEOUT = 60000 # 60 seconds

# Crop values
CROP_LEFT = 115
CROP_RIGHT_MARGIN = 115
CROP_TOP = 190
CROP_BOTTOM_MARGIN = 190

# Background color for the final canvas (White)
BG_COLOR = (248, 248, 249)

# CSS to hide UI elements before screenshot
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

        # Set viewport closer to target aspect ratio
        page = await browser.new_page(viewport={"width": OUTPUT_WIDTH, "height": OUTPUT_HEIGHT})

        print(f"Navigating to {URL}...")
        try:
            # Using 'domcontentloaded' might be faster if networkidle is too slow/unreliable
            await page.goto(URL, timeout=PAGE_LOAD_TIMEOUT, wait_until='domcontentloaded')
            print("Page navigation complete (DOM loaded).")
        except Exception as e:
            print(f"Error navigating to page or timeout exceeded: {e}")
            await browser.close()
            return

        print("Waiting briefly for initial script execution...")
        await asyncio.sleep(1) # Wait for JS to potentially modify the DOM initially

        print("Injecting CSS to hide UI elements...")
        try:
            await page.add_style_tag(content=HIDE_CSS)
            print("CSS injected.")
        except Exception as e:
            print(f"Error injecting CSS: {e}")
            # Continue anyway, maybe the elements aren't present

        print(f"Waiting for target element selector '{SELECTOR}'...")
        try:
            element = await page.wait_for_selector(SELECTOR, timeout=SELECTOR_TIMEOUT, state='visible')
            print("Target element found.")
        except Exception as e:
            print(f"Error finding target element selector or timeout exceeded: {e}")
            await browser.close()
            return

        # Give extra time for animations/rendering within the element to settle
        print("Waiting for artwork rendering...")
        # await asyncio.sleep(10) # Increased wait time after finding element

        # scroll down a bit
        await page.evaluate("window.scrollBy(0, 1000);")

        print("Taking screenshot of the element...")
        try:
            # screenshot_bytes = await element.screenshot()
            # take screenshot of the page instead and crop it later
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
        print(f"Original screenshot size: {img_w}x{img_h}")

        # --- Image Cropping Logic --- 
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
        # --- End Cropping Logic ---

        # Create a new blank image with the specified background color
        background = Image.new('RGB', (OUTPUT_WIDTH, OUTPUT_HEIGHT), BG_COLOR)
        print(f"Created background canvas: {OUTPUT_WIDTH}x{OUTPUT_HEIGHT} with color {BG_COLOR}")

        # Calculate position to paste the *cropped* image in the center
        offset_x = (OUTPUT_WIDTH - cropped_w) // 2
        offset_y = (OUTPUT_HEIGHT - cropped_h) // 2

        print(f"Pasting cropped image onto background at offset: ({offset_x}, {offset_y})")
        background.paste(cropped_img, (offset_x, offset_y))

        background.save(OUTPUT_FILENAME)
        print(f"Image saved as {OUTPUT_FILENAME} ({OUTPUT_WIDTH}x{OUTPUT_HEIGHT})")

if __name__ == "__main__":
    asyncio.run(main()) 
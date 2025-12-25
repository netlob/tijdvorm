import asyncio
import os
import time
from playwright.async_api import async_playwright
from PIL import ImageDraw

from backend.config import (
    URL, OUTPUT_WIDTH, OUTPUT_HEIGHT, PAGE_LOAD_TIMEOUT, 
    SELECTOR_TIMEOUT, RENDER_WAIT_TIME, SIMULATE_HOUR, 
    SLIDER_TRACK_SELECTOR, HIDE_CSS, ARTWORK_FRAME_SELECTOR,
    OUTPUT_FILENAME, MODIFIED_WEATHER_URL,
    TEMP_FONT_SIZE, COND_FONT_SIZE, TIME_FONT_SIZE, LINE_SPACING, TEXT_PADDING, TEXT_COLOR
)
from backend.utils.image import process_screenshot, load_fonts
from backend.integrations.weather import get_weather_data
from backend.integrations.home_assistant import get_home_temperature

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
    
    # Get the single font type loaded for different sizes
    font_temp = fonts.get('font_temp')
    font_cond = fonts.get('font_cond')
    font_time = fonts.get('font_time')
    
    # Calculate text block height
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

async def generate_timeform_image():
    """Orchestrates weather fetch, font load, screenshot, processing, overlay."""
    # 1. Fetch Weather Data
    weather_data = get_weather_data(MODIFIED_WEATHER_URL)
    text_data = {'temp': '--°C', 'condition': 'Weather unavailable', 'time': None, 'sauna': None}

    if weather_data and 'current' in weather_data:
        try:
            temp_c = weather_data['current']['temp_c']
            text_data['temp'] = f"{temp_c:.0f}°C"
            text_data['condition'] = weather_data['current']['condition']['text']
            if SIMULATE_HOUR is None and 'location' in weather_data and 'localtime' in weather_data['location']:
                 localtime = weather_data['location']['localtime']
                 time_parts = localtime.split(' '); text_data['time'] = time_parts[1] if len(time_parts) == 2 else None
        except KeyError as e: print(f"Warning: Could not extract weather data field: {e}")

    # Override with Home Assistant Temperature if available
    ha_temp = get_home_temperature()
    if ha_temp is not None:
        text_data['temp'] = f"{ha_temp:.0f}°C"

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


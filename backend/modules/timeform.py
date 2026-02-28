"""Timeform art generation — screenshots timeforms.app and adds weather overlay.

Two-phase rendering:
  1. generate_base() — expensive (Playwright browser), called every minute
  2. compose_frame() — cheap (PIL text draw), called every second for live clock
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from PIL import Image, ImageDraw
from playwright.async_api import async_playwright

from backend.config import (
    TIMEFORM_URL, OUTPUT_WIDTH, OUTPUT_HEIGHT, PAGE_LOAD_TIMEOUT,
    SELECTOR_TIMEOUT, RENDER_WAIT_TIME, SIMULATE_HOUR,
    SLIDER_TRACK_SELECTOR, HIDE_CSS, ARTWORK_FRAME_SELECTOR,
    TEMP_FONT_SIZE, COND_FONT_SIZE, TIME_FONT_SIZE, LINE_SPACING,
    TEXT_PADDING, TEXT_COLOR, WEATHER_URL,
)
from backend.utils.image import process_screenshot, load_fonts
from backend.integrations.weather import get_weather_data
from backend.integrations.home_assistant import get_home_temperature

logger = logging.getLogger("tijdvorm.timeform")


@dataclass
class TimeformBase:
    """Cached result of the expensive browser render."""
    image: Image.Image          # artwork without text overlay
    text_data: dict             # {"temp": "12°C", "condition": "Lichte regen"}
    fonts: dict                 # loaded PIL fonts
    align_artwork_top: bool     # text goes opposite side of artwork


async def _take_screenshot() -> bytes | None:
    """Launch browser, navigate to timeforms.app, capture screenshot."""
    logger.info("Launching browser...")
    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.chromium.launch()
        except Exception as e:
            logger.warning(f"Chromium failed: {e}, trying Firefox...")
            try:
                browser = await p.firefox.launch()
            except Exception as e2:
                logger.error(f"Firefox also failed: {e2}")
                return None
        if not browser:
            return None

        page = await browser.new_page(viewport={"width": OUTPUT_WIDTH, "height": OUTPUT_HEIGHT})
        try:
            logger.info(f"Navigating to {TIMEFORM_URL}...")
            await page.goto(TIMEFORM_URL, timeout=PAGE_LOAD_TIMEOUT, wait_until="networkidle")

            # Time simulation (if enabled)
            if SIMULATE_HOUR is not None and 0 <= SIMULATE_HOUR <= 23:
                logger.info(f"Simulating time: {SIMULATE_HOUR}:00")
                try:
                    slider = page.locator(SLIDER_TRACK_SELECTOR)
                    await slider.wait_for(state="visible", timeout=SELECTOR_TIMEOUT)
                    bbox = await slider.bounding_box()
                    if bbox:
                        click_x = bbox["x"] + (SIMULATE_HOUR / 23) * bbox["width"]
                        click_y = bbox["y"] + bbox["height"] / 2
                        await page.mouse.click(click_x, click_y)
                        await asyncio.sleep(1)
                except Exception as e:
                    logger.warning(f"Slider interaction failed: {e}")

            # Inject CSS to hide UI elements
            try:
                await page.add_style_tag(content=HIDE_CSS)
            except Exception as e:
                logger.warning(f"CSS injection failed: {e}")

            # Wait for artwork frame
            try:
                await page.locator(ARTWORK_FRAME_SELECTOR).wait_for(state="visible", timeout=SELECTOR_TIMEOUT)
                await asyncio.sleep(RENDER_WAIT_TIME)
            except Exception as e:
                logger.error(f"Artwork frame not found: {e}")
                return None

            return await page.screenshot()

        except Exception as e:
            logger.error(f"Browser error: {e}")
            return None
        finally:
            await browser.close()


def _draw_text_overlay(
    image: Image.Image,
    text_data: dict,
    fonts: dict,
    align_artwork_top: bool,
    time_str: str,
    dryer_minutes: int | None = None,
) -> Image.Image:
    """Draw weather/time text onto a copy of the image."""
    image = image.convert("RGBA")
    draw = ImageDraw.Draw(image)

    temp_str = text_data.get("temp", "--°C")
    cond_str = text_data.get("condition", "Unknown")
    dryer_str = f"Droger klaar over {dryer_minutes} min" if dryer_minutes is not None else None

    font_temp = fonts.get("font_temp")
    font_cond = fonts.get("font_cond")
    font_time = fonts.get("font_time")

    # Calculate text block height
    bbox_temp_h = TEMP_FONT_SIZE
    bbox_cond_h = COND_FONT_SIZE
    bbox_time_h = TIME_FONT_SIZE
    bbox_dryer_h = 0
    try:
        if font_temp:
            bbox_temp_h = draw.textbbox((0, 0), temp_str, font=font_temp)[3] - draw.textbbox((0, 0), temp_str, font=font_temp)[1]
        if font_cond:
            bbox_cond_h = draw.textbbox((0, 0), cond_str, font=font_cond)[3] - draw.textbbox((0, 0), cond_str, font=font_cond)[1]
        if font_time:
            bbox_time_h = draw.textbbox((0, 0), time_str, font=font_time)[3] - draw.textbbox((0, 0), time_str, font=font_time)[1]
        if dryer_str and font_cond:
            bbox_dryer_h = draw.textbbox((0, 0), dryer_str, font=font_cond)[3] - draw.textbbox((0, 0), dryer_str, font=font_cond)[1]
    except Exception:
        pass

    text_block_height = bbox_temp_h + LINE_SPACING + bbox_cond_h + LINE_SPACING + bbox_time_h
    if dryer_str:
        text_block_height += LINE_SPACING + bbox_dryer_h

    text_padding_y = TEXT_PADDING * 1.5
    text_at_top = not align_artwork_top
    text_y = text_padding_y if text_at_top else (OUTPUT_HEIGHT - text_block_height - text_padding_y)

    current_y = text_y
    text_padding_x = TEXT_PADDING
    try:
        if font_temp:
            draw.text((text_padding_x, current_y), temp_str, font=font_temp, fill=TEXT_COLOR)
            current_y += bbox_temp_h + (LINE_SPACING * 1.3)
        if font_cond:
            draw.text((text_padding_x, current_y), cond_str, font=font_cond, fill=TEXT_COLOR)
            current_y += bbox_cond_h + LINE_SPACING
        if font_time:
            draw.text((text_padding_x, current_y), time_str, font=font_time, fill=TEXT_COLOR)
            current_y += bbox_time_h + LINE_SPACING
        if dryer_str and font_cond:
            draw.text((text_padding_x, current_y), dryer_str, font=font_cond, fill=TEXT_COLOR)
    except Exception as e:
        logger.warning(f"Text drawing error: {e}")

    return image


def compose_frame(base: TimeformBase, dryer_minutes: int | None = None) -> Image.Image:
    """Compose a display-ready frame from a cached base — cheap, called every second."""
    time_str = time.strftime("%H:%M:%S")
    return _draw_text_overlay(
        base.image.copy(),
        base.text_data,
        base.fonts,
        base.align_artwork_top,
        time_str,
        dryer_minutes=dryer_minutes,
    )


async def generate_base() -> TimeformBase | None:
    """Generate the expensive base: browser screenshot + weather data + fonts.

    Returns a TimeformBase that can be passed to compose_frame() every second.
    """
    # Fetch weather
    weather_data = await get_weather_data(WEATHER_URL)
    text_data = {"temp": "--°C", "condition": "Weather unavailable"}

    if weather_data and "current" in weather_data:
        try:
            text_data["temp"] = f"{weather_data['current']['temp_c']:.0f}°C"
            text_data["condition"] = weather_data["current"]["condition"]["text"]
        except KeyError:
            pass

    # Override with HA home temperature
    ha_temp = await get_home_temperature()
    if ha_temp is not None:
        text_data["temp"] = f"{ha_temp:.0f}°C"

    # Load fonts
    fonts = load_fonts()
    if not fonts.get("font_temp") or not fonts.get("font_cond"):
        logger.error("Essential fonts could not be loaded")
        return None

    # Take screenshot
    screenshot_bytes = await _take_screenshot()
    if not screenshot_bytes:
        logger.error("Screenshot failed")
        return None

    # Process (crop, zoom, align)
    background_image, align_artwork_top = process_screenshot(screenshot_bytes)
    if not background_image:
        logger.error("Screenshot processing failed")
        return None

    return TimeformBase(
        image=background_image,
        text_data=text_data,
        fonts=fonts,
        align_artwork_top=align_artwork_top,
    )

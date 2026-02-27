"""Sauna status display — generates an image showing sauna temp, ETA, outdoor weather."""

import json
import logging
import os
import time

from PIL import Image, ImageDraw

from backend.config import (
    WEATHER_URL, OUTPUT_WIDTH, OUTPUT_HEIGHT, FONT_PATH,
    COND_FONT_SIZE, TEXT_PADDING, LINE_SPACING, TEXT_COLOR,
    SAUNA_LOG_FILE, SAUNA_BACKGROUND_PATH,
)
from backend.utils.image import load_fonts, load_font_with_fallback
from backend.integrations.weather import get_weather_data
from backend.integrations.home_assistant import get_home_temperature, get_power_usage

logger = logging.getLogger("tijdvorm.sauna")


def _update_prediction(current_temp: float, set_temp: float) -> str | None:
    """Update sauna heating log and return ETA prediction string."""
    try:
        now = time.time()
        log_data = {"peak_temp": 0.0, "history": []}

        if os.path.exists(SAUNA_LOG_FILE):
            try:
                with open(SAUNA_LOG_FILE, "r") as f:
                    log_data = json.load(f)
            except Exception:
                pass

        peak = log_data.get("peak_temp", 0.0)
        history = log_data.get("history", [])

        # Reset if temp dropped significantly
        if peak > 0 and current_temp < (0.5 * peak):
            log_data = {"peak_temp": current_temp, "history": []}
            peak = current_temp
            history = []

        if current_temp > peak:
            log_data["peak_temp"] = current_temp

        history.append({"ts": now, "temp": current_temp})

        # Keep last 3 hours
        cutoff = now - (3 * 3600)
        history = [h for h in history if h["ts"] > cutoff]
        log_data["history"] = history

        try:
            with open(SAUNA_LOG_FILE, "w") as f:
                json.dump(log_data, f)
        except Exception as e:
            logger.warning(f"Could not save sauna log: {e}")

        # Prediction
        if len(history) < 2:
            return None

        if current_temp >= set_temp:
            return "BASTUUUUU COOKING TOOOT"

        # Use last 15 minutes for rate
        window_start = now - (15 * 60)
        recent = [h for h in history if h["ts"] >= window_start]
        if len(recent) < 2:
            recent = history
        if len(recent) < 2:
            return None

        temp_diff = recent[-1]["temp"] - recent[0]["temp"]
        time_diff_min = (recent[-1]["ts"] - recent[0]["ts"]) / 60.0

        if time_diff_min <= 0 or temp_diff <= 0:
            return None

        rate = temp_diff / time_diff_min
        remaining = set_temp - current_temp
        if remaining <= 0:
            return "BASTUUUUU COOKING TOOOT!"

        minutes_left = remaining / rate
        if minutes_left > 120:
            return "Bastu maakt geen progress"

        return f"Bastu ready in ~{minutes_left:.0f} min"

    except Exception as e:
        logger.warning(f"Prediction error: {e}")
        return None


async def generate(sauna_status: dict) -> Image.Image | None:
    """Generate sauna status image. Returns PIL Image."""
    logger.info("Generating sauna image...")

    # Fetch weather
    weather_data = await get_weather_data(WEATHER_URL)
    temp_c_str = "--°C"
    weather_desc = ""
    if weather_data and "current" in weather_data:
        try:
            temp_c_str = f"{weather_data['current']['temp_c']:.0f}°C"
            weather_desc = weather_data["current"]["condition"]["text"]
        except Exception:
            pass

    ha_temp = await get_home_temperature()
    if ha_temp is not None:
        temp_c_str = f"{ha_temp:.0f}°C"

    power_watts = await get_power_usage()
    power_str = None
    if power_watts is not None:
        formatted = "{:,.0f}".format(power_watts).replace(",", ".")
        power_str = f"{formatted}W"

    # Fonts
    fonts = load_fonts(scale=1.2)
    if not fonts.get("font_temp"):
        logger.error("Essential fonts could not be loaded")
        return None

    font_outdoor = load_font_with_fallback(FONT_PATH, int(COND_FONT_SIZE * 0.9))
    if not font_outdoor:
        font_outdoor = fonts.get("font_cond")

    # Background
    bg_path = os.path.abspath(SAUNA_BACKGROUND_PATH)
    if not os.path.exists(bg_path):
        logger.error(f"Sauna background not found: {bg_path}")
        return None

    try:
        img = Image.open(bg_path).convert("RGBA")
        if img.size != (OUTPUT_WIDTH, OUTPUT_HEIGHT):
            img = img.resize((OUTPUT_WIDTH, OUTPUT_HEIGHT), Image.Resampling.LANCZOS)
    except Exception as e:
        logger.error(f"Background load error: {e}")
        return None

    draw = ImageDraw.Draw(img)

    # Text content
    set_temp_str = f"{sauna_status.get('set_temp', 0):.0f}°C"
    cur_val = float(sauna_status.get("current_temp", 0))
    combined_temp = f"{cur_val:.0f}°C / {set_temp_str}"
    time_str = time.strftime("%H:%M")
    outdoor_line = f"{temp_c_str}  {time_str}"
    prediction = _update_prediction(cur_val, float(sauna_status.get("set_temp", 0)))

    font_title = fonts.get("font_cond")
    font_big = fonts.get("font_temp")
    font_sub = fonts.get("font_cond")

    padding_x = TEXT_PADDING
    padding_y = TEXT_PADDING * 1.5
    spacing = LINE_SPACING * 1.2

    try:
        # Top left: sauna status
        y = padding_y
        if font_title:
            draw.text((padding_x, y), "Cooking tot", font=font_title, fill=TEXT_COLOR)
            bbox = draw.textbbox((0, 0), "Cooking tot", font=font_title)
            y += (bbox[3] - bbox[1]) + spacing

        if font_big:
            draw.text((padding_x, y), combined_temp, font=font_big, fill=TEXT_COLOR)
            bbox = draw.textbbox((0, 0), combined_temp, font=font_big)
            y += (bbox[3] - bbox[1]) + spacing

        if power_str and font_sub:
            draw.text((padding_x, y), power_str, font=font_sub, fill=TEXT_COLOR)

        # Top right: outdoor
        right_x = OUTPUT_WIDTH - TEXT_PADDING
        y_right = padding_y
        if font_outdoor:
            w = draw.textlength("Buiten", font=font_outdoor)
            draw.text((right_x - w, y_right), "Buiten", font=font_outdoor, fill=TEXT_COLOR)
            bbox = draw.textbbox((0, 0), "Buiten", font=font_outdoor)
            y_right += (bbox[3] - bbox[1]) + spacing

            w = draw.textlength(outdoor_line, font=font_outdoor)
            draw.text((right_x - w, y_right), outdoor_line, font=font_outdoor, fill=TEXT_COLOR)
            bbox = draw.textbbox((0, 0), outdoor_line, font=font_outdoor)
            y_right += (bbox[3] - bbox[1]) + spacing

            if weather_desc:
                w = draw.textlength(weather_desc, font=font_outdoor)
                draw.text((right_x - w, y_right), weather_desc, font=font_outdoor, fill=TEXT_COLOR)

        # Bottom center: prediction
        if prediction and font_sub:
            w = draw.textlength(prediction, font=font_sub)
            draw.text((OUTPUT_WIDTH // 2 - w / 2, 1800), prediction, font=font_sub, fill=TEXT_COLOR)

    except Exception as e:
        logger.error(f"Drawing error: {e}")
        return None

    return img

"""Sauna status display — generates an image showing sauna temp, ETA, outdoor weather.

Uses a two-phase pattern (like timeform):
  generate_base()  — expensive: load background, fonts, weather (cached)
  compose_frame()  — cheap: draw dynamic text every second (temp, watts, time, prediction)
"""

import json
import logging
import os
import time
from dataclasses import dataclass

from PIL import Image, ImageDraw

from backend.config import (
    WEATHER_URL, OUTPUT_WIDTH, OUTPUT_HEIGHT, FONT_PATH,
    COND_FONT_SIZE, TEXT_PADDING, LINE_SPACING, TEXT_COLOR,
    SAUNA_LOG_FILE, SAUNA_BACKGROUND_PATH,
)
from backend.utils.image import load_fonts, load_font_with_fallback
from backend.integrations.weather import get_weather_data
from backend.integrations.home_assistant import get_home_temperature

logger = logging.getLogger("tijdvorm.sauna")


# ── SaunaBase: cached expensive data ────────────────────────────────

@dataclass
class SaunaBase:
    """Cached result of the expensive sauna frame setup."""
    background: Image.Image          # Pre-loaded, pre-resized RGBA background
    fonts: dict                      # font_title, font_big, font_sub, font_outdoor
    weather_temp_str: str            # e.g. "4°C"
    weather_desc: str                # e.g. "Lichte regen"


# ── In-memory prediction state ──────────────────────────────────────

_prediction_history: list[dict] = []
_prediction_peak: float = 0.0
_last_disk_write: float = 0.0
_last_sample_time: float = 0.0
_DISK_WRITE_INTERVAL = 30.0          # seconds between disk persists
_SAMPLE_INTERVAL = 30.0              # seconds between history samples


def init_prediction():
    """Load persisted sauna_log.json into memory."""
    global _prediction_history, _prediction_peak, _last_disk_write, _last_sample_time
    try:
        if os.path.exists(SAUNA_LOG_FILE):
            with open(SAUNA_LOG_FILE, "r") as f:
                log_data = json.load(f)
            _prediction_peak = log_data.get("peak_temp", 0.0)
            _prediction_history = log_data.get("history", [])
            cutoff = time.time() - (3 * 3600)
            _prediction_history = [h for h in _prediction_history if h["ts"] > cutoff]
        else:
            _prediction_history = []
            _prediction_peak = 0.0
    except Exception as e:
        logger.warning(f"Could not load sauna log: {e}")
        _prediction_history = []
        _prediction_peak = 0.0
    _last_disk_write = time.time()
    _last_sample_time = 0.0


def _persist_to_disk():
    """Write current in-memory prediction state to sauna_log.json."""
    try:
        log_data = {"peak_temp": _prediction_peak, "history": _prediction_history}
        with open(SAUNA_LOG_FILE, "w") as f:
            json.dump(log_data, f)
    except Exception as e:
        logger.warning(f"Could not save sauna log: {e}")


def flush_prediction():
    """Persist final state to disk when sauna deactivates."""
    _persist_to_disk()


def update_prediction(current_temp: float, set_temp: float) -> str | None:
    """Update in-memory history and return ETA prediction string.

    Called every second from compose_frame.  Only samples a new data
    point every _SAMPLE_INTERVAL seconds and persists to disk every
    _DISK_WRITE_INTERVAL seconds.
    """
    global _prediction_history, _prediction_peak, _last_disk_write, _last_sample_time

    try:
        now = time.time()

        # Reset if temp dropped significantly (sauna cooled down)
        if _prediction_peak > 0 and current_temp < (0.5 * _prediction_peak):
            _prediction_history = []
            _prediction_peak = current_temp

        if current_temp > _prediction_peak:
            _prediction_peak = current_temp

        # Sample every ~30s to keep history manageable
        if now - _last_sample_time >= _SAMPLE_INTERVAL:
            _prediction_history.append({"ts": now, "temp": current_temp})
            _last_sample_time = now
            # Trim to last 3 hours
            cutoff = now - (3 * 3600)
            _prediction_history = [h for h in _prediction_history if h["ts"] > cutoff]

        # Persist to disk periodically
        if now - _last_disk_write >= _DISK_WRITE_INTERVAL:
            _persist_to_disk()
            _last_disk_write = now

        # ── Compute prediction ──
        if len(_prediction_history) < 2:
            return None

        if current_temp >= set_temp:
            return "BASTUUUUU COOKING TOOOT"

        # Use last 15 minutes for rate (natural smoothing)
        window_start = now - (15 * 60)
        recent = [h for h in _prediction_history if h["ts"] >= window_start]
        if len(recent) < 2:
            recent = _prediction_history
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


# ── Base generation (expensive, cached) ─────────────────────────────

async def generate_base(sauna_status: dict) -> SaunaBase | None:
    """Generate the expensive base: load background, fetch weather, load fonts.

    Called once when sauna activates, then again every UPDATE_INTERVAL_MINUTES.
    """
    logger.info("Generating sauna base...")

    init_prediction()

    # Fetch weather (slow network call — cached in base)
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

    # Fonts
    fonts_raw = load_fonts(scale=1.2)
    if not fonts_raw.get("font_temp"):
        logger.error("Essential fonts could not be loaded")
        return None

    font_outdoor = load_font_with_fallback(FONT_PATH, int(COND_FONT_SIZE * 0.9))
    if not font_outdoor:
        font_outdoor = fonts_raw.get("font_cond")

    fonts = {
        "font_title": fonts_raw.get("font_cond"),
        "font_big": fonts_raw.get("font_temp"),
        "font_sub": fonts_raw.get("font_cond"),
        "font_outdoor": font_outdoor,
    }

    # Background
    bg_path = os.path.abspath(SAUNA_BACKGROUND_PATH)
    if not os.path.exists(bg_path):
        logger.error(f"Sauna background not found: {bg_path}")
        return None

    try:
        bg = Image.open(bg_path).convert("RGBA")
        if bg.size != (OUTPUT_WIDTH, OUTPUT_HEIGHT):
            bg = bg.resize((OUTPUT_WIDTH, OUTPUT_HEIGHT), Image.Resampling.LANCZOS)
    except Exception as e:
        logger.error(f"Background load error: {e}")
        return None

    return SaunaBase(
        background=bg,
        fonts=fonts,
        weather_temp_str=temp_c_str,
        weather_desc=weather_desc,
    )


# ── Frame composition (cheap, every second) ─────────────────────────

def compose_frame(
    base: SaunaBase,
    sauna_status: dict,
    power_watts: float | None = None,
) -> Image.Image:
    """Compose a display-ready frame from cached base — called every second."""
    img = base.background.copy()
    draw = ImageDraw.Draw(img)

    set_temp = float(sauna_status.get("set_temp", 0))
    cur_val = float(sauna_status.get("current_temp", 0))
    combined_temp = f"{cur_val:.0f}°C / {set_temp:.0f}°C"
    time_str = time.strftime("%H:%M:%S")
    outdoor_line = f"Buiten {base.weather_temp_str}"
    time_line = time_str

    power_str = None
    if power_watts is not None:
        formatted = "{:,.0f}".format(power_watts).replace(",", ".")
        power_str = f"{formatted}W"

    prediction = update_prediction(cur_val, set_temp)

    font_title = base.fonts.get("font_title")
    font_big = base.fonts.get("font_big")
    font_sub = base.fonts.get("font_sub")
    font_outdoor = base.fonts.get("font_outdoor")

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
            w = draw.textlength(outdoor_line, font=font_outdoor)
            draw.text((right_x - w, y_right), outdoor_line, font=font_outdoor, fill=TEXT_COLOR)
            bbox = draw.textbbox((0, 0), outdoor_line, font=font_outdoor)
            y_right += (bbox[3] - bbox[1]) + spacing

            w = draw.textlength(time_line, font=font_outdoor)
            draw.text((right_x - w, y_right), time_line, font=font_outdoor, fill=TEXT_COLOR)
            bbox = draw.textbbox((0, 0), time_line, font=font_outdoor)
            y_right += (bbox[3] - bbox[1]) + spacing

            if base.weather_desc:
                w = draw.textlength(base.weather_desc, font=font_outdoor)
                draw.text((right_x - w, y_right), base.weather_desc, font=font_outdoor, fill=TEXT_COLOR)

        # Bottom center: prediction
        if prediction and font_sub:
            w = draw.textlength(prediction, font=font_sub)
            draw.text((OUTPUT_WIDTH // 2 - w / 2, 1800), prediction, font=font_sub, fill=TEXT_COLOR)

    except Exception as e:
        logger.error(f"Sauna compose drawing error: {e}")

    return img

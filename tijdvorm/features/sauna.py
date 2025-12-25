import time
import os
import json
from PIL import Image, ImageDraw

from tijdvorm.config import (
    MODIFIED_WEATHER_URL, OUTPUT_WIDTH, OUTPUT_HEIGHT, 
    OUTPUT_FILENAME, FONT_PATH, COND_FONT_SIZE, 
    TEXT_PADDING, LINE_SPACING, TEXT_COLOR, SAUNA_LOG_FILE,
    SAUNA_BACKGROUND_PATH
)
from tijdvorm.utils.image import load_fonts, load_font_with_fallback
from tijdvorm.integrations.weather import get_weather_data
from tijdvorm.integrations.home_assistant import (
    get_home_temperature, get_power_usage
)

def update_sauna_prediction(current_temp, set_temp):
    """
    Updates the sauna log and returns a prediction string (e.g., 'ETA: 20 min').
    Handles resetting the log if temp drops significantly.
    """
    try:
        now = time.time()
        log_data = {"peak_temp": 0.0, "history": []}
        
        # Load existing log
        if os.path.exists(SAUNA_LOG_FILE):
            try:
                with open(SAUNA_LOG_FILE, "r") as f:
                    log_data = json.load(f)
            except Exception:
                pass # Corrupt or empty, start fresh

        peak = log_data.get("peak_temp", 0.0)
        history = log_data.get("history", [])

        # Check Reset Condition (drop < 50% of peak)
        # We only check this if we have a peak established > 0
        if peak > 0 and current_temp < (0.5 * peak):
            print(f"Sauna temp dropped significantly ({current_temp} < 0.5 * {peak}). Resetting log.")
            log_data = {"peak_temp": current_temp, "history": []}
            peak = current_temp
            history = []

        # Update Peak
        if current_temp > peak:
            log_data["peak_temp"] = current_temp
            peak = current_temp

        # Append current measurement
        history.append({"ts": now, "temp": current_temp})
        
        # Keep only last 3 hours of history to avoid indefinite growth
        cutoff = now - (3 * 3600)
        history = [h for h in history if h["ts"] > cutoff]
        
        log_data["history"] = history
        
        # Save Log
        try:
            with open(SAUNA_LOG_FILE, "w") as f:
                json.dump(log_data, f)
        except Exception as e:
            print(f"Warning: Could not save sauna log: {e}")

        # --- Prediction Logic ---
        if len(history) < 2:
            return None # Not enough data
            
        if current_temp >= set_temp:
            return "BASTUUUUU COOKING TOOOT"

        # Use recent history (last 15 minutes) for prediction
        window_start = now - (15 * 60)
        recent_points = [h for h in history if h["ts"] >= window_start]
        
        if len(recent_points) < 2:
            # Fallback to all history if recent is sparse
            recent_points = history

        if len(recent_points) < 2:
             return None

        # Calculate Rate (deg/min)
        # Simple slope: (last - first) / time_diff
        first_pt = recent_points[0]
        last_pt = recent_points[-1]
        
        temp_diff = last_pt["temp"] - first_pt["temp"]
        time_diff_min = (last_pt["ts"] - first_pt["ts"]) / 60.0
        
        if time_diff_min <= 0 or temp_diff <= 0:
            return None # Not heating or invalid time

        rate = temp_diff / time_diff_min # degrees per minute
        
        remaining_temp = set_temp - current_temp
        if remaining_temp <= 0:
            return "BASTUUUUU COOKING TOOOT!"
            
        minutes_left = remaining_temp / rate
        
        # Cap prediction at reasonable bounds (e.g. 120 mins)
        if minutes_left > 120:
            return "Bastu maakt geen progress"
            
        return f"Bastu ready in ~{minutes_left:.0f} min"

    except Exception as e:
        print(f"Error in sauna prediction: {e}")
        return None

async def generate_sauna_image(sauna_status):
    """Generates the sauna status image using the background."""
    print("Generating Sauna image...")
    
    # 1. Fetch Weather Data (for outdoor temp)
    weather_data = get_weather_data(MODIFIED_WEATHER_URL)
    temp_c_str = '--°C'
    weather_desc_str = ""
    if weather_data and 'current' in weather_data:
        try:
            temp_c = weather_data['current']['temp_c']
            temp_c_str = f"{temp_c:.0f}°C"
            weather_desc_str = weather_data['current']['condition']['text']
        except Exception: pass

    # Override with Home Assistant Temperature if available
    ha_temp = get_home_temperature()
    if ha_temp is not None:
        temp_c_str = f"{ha_temp:.0f}°C"

    # Fetch Power Data
    power_watts = get_power_usage()
    power_str = None
    if power_watts is not None:
        # Format: 1.000W
        # Use comma as thousand sep then replace with dot
        formatted_w = "{:,.0f}".format(power_watts).replace(",", ".")
        power_str = f"{formatted_w}W"

    # 2. Load Fonts (scaled)
    # Reducing scale as requested (was 1.5)
    fonts = load_fonts(scale=1.2)
    if not fonts.get('font_temp'):
        print("Error: Essential fonts could not be loaded."); return None
    
    # Load separate smaller font for outdoor elements (scale 0.9)
    font_outdoor_small = load_font_with_fallback(FONT_PATH, int(COND_FONT_SIZE * 0.9))
    if not font_outdoor_small:
        # Fallback to normal font_cond if load fails
        font_outdoor_small = fonts.get('font_cond')

    # 3. Load Background
    bg_path = os.path.abspath(SAUNA_BACKGROUND_PATH)
    if not os.path.exists(bg_path):
        print(f"Error: Sauna background not found at {bg_path}")
        return None
    
    try:
        img = Image.open(bg_path).convert("RGBA")
        # Resize to output dimensions if needed
        if img.size != (OUTPUT_WIDTH, OUTPUT_HEIGHT):
             img = img.resize((OUTPUT_WIDTH, OUTPUT_HEIGHT), Image.Resampling.LANCZOS)
    except Exception as e:
        print(f"Error loading sauna background: {e}")
        return None

    draw = ImageDraw.Draw(img)
    
    # 4. Draw Text
    
    title_str = "Cooking tot"
    set_temp_str = f"{sauna_status.get('set_temp', 0):.0f}°C"
    
    cur_val = float(sauna_status.get('current_temp', 0))
    current_temp_str = f"{cur_val:.0f}°C"
    
    # Combined Temp String: "45°C / 80°C"
    combined_temp_str = f"{current_temp_str} / {set_temp_str}"

    # Outdoor strings
    outdoor_title_str = "Buiten"
    time_str = time.strftime("%H:%M")
    outdoor_line_2 = f"{temp_c_str}  {time_str}"
    
    # Calculate Prediction
    prediction_str = update_sauna_prediction(cur_val, float(sauna_status.get('set_temp', 0)))

    font_title = fonts.get('font_cond') # Use condition font for title
    font_set = fonts.get('font_temp') # Use big temp font for set temp (using for combined)
    font_sub = fonts.get('font_cond') # Use condition font for sub-line
    # font_time = fonts.get('font_time')

    # Top Section Layout
    text_padding_x = TEXT_PADDING
    text_padding_y = TEXT_PADDING * 1.5
    current_y = text_padding_y
    line_spacing_scaled = LINE_SPACING * 1.2

    try:
        # --- Top Left: Sauna Status ---
        if font_title:
            draw.text((text_padding_x, current_y), title_str, font=font_title, fill=TEXT_COLOR)
            bbox = draw.textbbox((0, 0), title_str, font=font_title)
            current_y += (bbox[3] - bbox[1]) + line_spacing_scaled

        if font_set:
            draw.text((text_padding_x, current_y), combined_temp_str, font=font_set, fill=TEXT_COLOR)
            bbox = draw.textbbox((0, 0), combined_temp_str, font=font_set)
            current_y += (bbox[3] - bbox[1]) + line_spacing_scaled

        if power_str and font_sub:
            draw.text((text_padding_x, current_y), power_str, font=font_sub, fill=TEXT_COLOR)
            
        # --- Top Right: Outdoor Status ---
        # Aligned to right margin (OUTPUT_WIDTH - TEXT_PADDING)
        right_margin_x = OUTPUT_WIDTH - TEXT_PADDING
        current_y_right = text_padding_y
        
        if font_outdoor_small:
             w_title = draw.textlength(outdoor_title_str, font=font_outdoor_small)
             draw.text((right_margin_x - w_title, current_y_right), outdoor_title_str, font=font_outdoor_small, fill=TEXT_COLOR)
             bbox = draw.textbbox((0, 0), outdoor_title_str, font=font_outdoor_small)
             current_y_right += (bbox[3] - bbox[1]) + line_spacing_scaled
             
             w_line2 = draw.textlength(outdoor_line_2, font=font_outdoor_small)
             draw.text((right_margin_x - w_line2, current_y_right), outdoor_line_2, font=font_outdoor_small, fill=TEXT_COLOR)
             bbox = draw.textbbox((0, 0), outdoor_line_2, font=font_outdoor_small)
             current_y_right += (bbox[3] - bbox[1]) + line_spacing_scaled
             
             if weather_desc_str:
                 w_desc = draw.textlength(weather_desc_str, font=font_outdoor_small)
                 draw.text((right_margin_x - w_desc, current_y_right), weather_desc_str, font=font_outdoor_small, fill=TEXT_COLOR)

        # --- Bottom Center: Prediction (was Power) ---
        # y = 1800
        if prediction_str and font_sub: 
             w_pred = draw.textlength(prediction_str, font=font_sub)
             center_x = OUTPUT_WIDTH // 2
             draw.text((center_x - (w_pred / 2), 1800), prediction_str, font=font_sub, fill=TEXT_COLOR)

    except Exception as e:
        print(f"Error drawing sauna text: {e}")
        return None

    # Rotate 180
    final_image = img.rotate(180)

    # Save
    try:
        abs_output_path = os.path.abspath(OUTPUT_FILENAME)
        final_image.save(abs_output_path)
        print(f"Sauna image generated and saved successfully as {abs_output_path}")
        return abs_output_path
    except Exception as e:
        print(f"Error saving sauna image: {e}")
        return None

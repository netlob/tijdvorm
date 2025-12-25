import io
import os
from PIL import Image, ImageDraw, ImageFont
from tijdvorm.config import (
    FONT_PATH, TEMP_FONT_SIZE, COND_FONT_SIZE, TIME_FONT_SIZE,
    CROP_LEFT, CROP_TOP, CROP_RIGHT_MARGIN, CROP_BOTTOM_MARGIN,
    ZOOM_FACTOR, OUTPUT_WIDTH, OUTPUT_HEIGHT, COLOR_TOLERANCE
)

def color_diff(color1, color2):
    """Calculate the sum of absolute differences between two RGB tuples."""
    if not color1 or not color2 or len(color1) < 3 or len(color2) < 3:
        return float('inf')
    return sum(abs(c1 - c2) for c1, c2 in zip(color1[:3], color2[:3]))

def load_font_with_fallback(font_path, size):
    """Load font from a specific path, falling back to Pillow default."""
    abs_path = os.path.abspath(font_path)
    # print(f"[Font Load] Attempting to load: {abs_path}")
    try:
        font = ImageFont.truetype(abs_path, size)
        # print(f"[Font Load] Successfully loaded: {abs_path}")
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

def load_fonts(scale=1.0):
    """Load all required fonts using the specified path."""
    print(f"Loading fonts (scale={scale})...")
    fonts = {
        'font_temp': load_font_with_fallback(FONT_PATH, int(TEMP_FONT_SIZE * scale)),
        'font_cond': load_font_with_fallback(FONT_PATH, int(COND_FONT_SIZE * scale)),
        'font_time': load_font_with_fallback(FONT_PATH, int(TIME_FONT_SIZE * scale))
    }
    return fonts

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


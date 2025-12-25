import os

# --- Samsung TV Config ---
TV_IP = "10.0.1.111" # !!! REPLACE WITH YOUR TV's IP ADDRESS !!!
UPDATE_INTERVAL_MINUTES = 1
DELETE_OLD_ART = True # turn on to always delete all manually uploaded art

# --- Configuration Constants ---
WEATHER_LOCATION = "Nieuw-Vennep,NL"
URL = "https://timeforms.app"

# Selectors
ARTWORK_FRAME_SELECTOR = "#root > div.w-full.min-h-screen.flex.items-center.justify-center.p-8.transition-colors.duration-1000.relative > div.absolute.top-1\\/2.left-1\\/2.-translate-y-1\\/2.-translate-x-1\\/2.w-full.flex.justify-center.items-center > div > div"
SLIDER_TRACK_SELECTOR = 'span.relative.flex.touch-none.select-none.items-center.w-full.slider-custom'

# Output
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FILENAME = "timeform_art.png"

# Data Directories
DATA_DIR = "./data"
IMAGES_DIR = os.path.join(DATA_DIR, "images")
EASTER_EGGS_DIR = os.path.join(IMAGES_DIR, "eastereggs")
ROTATED_IMAGES_DIR = os.path.join(EASTER_EGGS_DIR, "rotated")
LIVE_DIR = os.path.join(DATA_DIR, "live")
ASSETS_DIR = "./assets"

# Asset Paths
FONT_PATH = os.path.join(ASSETS_DIR, "fonts/SFNS.ttf")
SAUNA_BACKGROUND_PATH = os.path.join(ASSETS_DIR, "sauna_background.png")

# Database/State Files
EASTER_EGGS_MANIFEST = os.path.join(DATA_DIR, "manifest.json")
EASTER_EGGS_OVERRIDE = os.path.join(DATA_DIR, "override.json")
EASTER_EGGS_SETTINGS = os.path.join(DATA_DIR, "settings.json")
SAUNA_LOG_FILE = os.path.join(DATA_DIR, "sauna_log.json")
LIVE_PREVIEW_FILENAME = "preview.png"
LIVE_STATE_FILENAME = "state.json" # Kept in live/ for now as it relates to preview.png

# Face Recognition
FACES_DIR = os.path.join(DATA_DIR, "faces")
ENCODINGS_FILE = os.path.join(DATA_DIR, "face_encodings.pickle")

# Home Assistant
HA_EXPLICIT_ENTITY = os.environ.get("HA_EXPLICIT_ENTITY", "input_boolean.explicit_frame_art")
HA_DOORBELL_ACTIVE_ENTITY = os.environ.get("HA_DOORBELL_ACTIVE_ENTITY", "input_boolean.doorbell_active")
HA_SAUNA_ENTITY = os.environ.get("HA_SAUNA_ENTITY", "climate.sauna_control")
HA_POWER_ENTITY = os.environ.get("HA_POWER_ENTITY", "sensor.power_consumed")
HA_TEMP_ENTITY = os.environ.get("HA_TEMP_ENTITY", "sensor.inieuw549_temperature")
HA_BASE_URL = os.environ.get("HA_BASE_URL", "").rstrip("/")  # e.g. https://ha.example.com
HA_TOKEN = os.environ.get("HA_TOKEN", "")
HA_TIMEOUT_SECONDS = float(os.environ.get("HA_TIMEOUT_SECONDS", "2.0"))
HA_CACHE_TTL_SECONDS = float(os.environ.get("HA_CACHE_TTL_SECONDS", "30.0"))

# Doorbell Configuration
USE_PYTHON_DOORBELL_PUSH = False # Set to False if HA handles the display via media_player

# Playwright Timing
PAGE_LOAD_TIMEOUT = 90000
SELECTOR_TIMEOUT = 60000
RENDER_WAIT_TIME = 3 # Seconds to wait after page actions for rendering

# Simulation
SIMULATE_HOUR = None # Set hour (0-23) or None

# Weather API
# Note: Key is hardcoded in original file. Kept here.
MODIFIED_WEATHER_URL = f"https://api.weatherapi.com/v1/current.json?key=8cd71ded6ce646e888600951251504&q={WEATHER_LOCATION}&lang=NL"

# Font Configuration
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

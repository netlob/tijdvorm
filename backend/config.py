import os

# --- Output ---
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920

# --- Data Directories ---
DATA_DIR = os.environ.get("DATA_DIR", "./data")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
EASTER_EGGS_DIR = os.path.join(IMAGES_DIR, "eastereggs")
LIVE_DIR = os.path.join(DATA_DIR, "live")
ASSETS_DIR = os.environ.get("ASSETS_DIR", "./assets")

# Asset Paths
FONT_PATH = os.path.join(ASSETS_DIR, "fonts/SFNS.ttf")
SAUNA_BACKGROUND_PATH = os.path.join(ASSETS_DIR, "sauna_background.png")

# State Files
EASTER_EGGS_MANIFEST = os.path.join(DATA_DIR, "manifest.json")
EASTER_EGGS_OVERRIDE = os.path.join(DATA_DIR, "override.json")
EASTER_EGGS_SETTINGS = os.path.join(DATA_DIR, "settings.json")
SAUNA_LOG_FILE = os.path.join(DATA_DIR, "sauna_log.json")
LIVE_PREVIEW_PATH = os.path.join(LIVE_DIR, "preview.png")
LIVE_STATE_PATH = os.path.join(LIVE_DIR, "state.json")

# --- Home Assistant ---
HA_BASE_URL = os.environ.get("HA_BASE_URL", "").rstrip("/")
HA_TOKEN = os.environ.get("HA_TOKEN", "")
HA_TIMEOUT_SECONDS = float(os.environ.get("HA_TIMEOUT_SECONDS", "2.0"))
HA_CACHE_TTL_SECONDS = float(os.environ.get("HA_CACHE_TTL_SECONDS", "30.0"))

HA_TV_ENTITY = os.environ.get("HA_TV_ENTITY", "input_boolean.frame_tv_active")
HA_EXPLICIT_ENTITY = os.environ.get("HA_EXPLICIT_ENTITY", "input_boolean.explicit_frame_art")
HA_DOORBELL_ACTIVE_ENTITY = os.environ.get("HA_DOORBELL_ACTIVE_ENTITY", "input_boolean.doorbell_active")
HA_SAUNA_ENTITY = os.environ.get("HA_SAUNA_ENTITY", "climate.sauna_control")
HA_POWER_ENTITY = os.environ.get("HA_POWER_ENTITY", "sensor.power_consumed")
HA_TEMP_ENTITY = os.environ.get("HA_TEMP_ENTITY", "sensor.inieuw549_temperature")

# --- Doorbell ---
NVR_RTSP_URL = os.environ.get(
    "NVR_RTSP_URL",
    "rtsp://admin:peepeeDoorbell%24123poopoo@10.0.1.45:554/h264Preview_01_main",
)

# --- Timeform ---
TIMEFORM_URL = os.environ.get("TIMEFORM_URL", "https://timeforms.app")

ARTWORK_FRAME_SELECTOR = "#root > div.w-full.min-h-screen.flex.items-center.justify-center.p-8.transition-colors.duration-1000.relative > div.absolute.top-1\\/2.left-1\\/2.-translate-y-1\\/2.-translate-x-1\\/2.w-full.flex.justify-center.items-center > div > div"
SLIDER_TRACK_SELECTOR = "span.relative.flex.touch-none.select-none.items-center.w-full.slider-custom"

PAGE_LOAD_TIMEOUT = 90000
SELECTOR_TIMEOUT = 60000
RENDER_WAIT_TIME = 3  # seconds

SIMULATE_HOUR = None  # Set hour (0-23) or None

# --- Weather ---
WEATHER_LOCATION = "Nieuw-Vennep,NL"
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "8cd71ded6ce646e888600951251504")
WEATHER_URL = f"https://api.weatherapi.com/v1/current.json?key={WEATHER_API_KEY}&q={WEATHER_LOCATION}&lang=NL"

# --- Font / Text ---
TEMP_FONT_SIZE = 63
COND_FONT_SIZE = 47
TIME_FONT_SIZE = 39
TEXT_COLOR = (75, 85, 99)
TEXT_PADDING = 75
LINE_SPACING = 26

# --- Image Processing ---
CROP_LEFT = 90
CROP_RIGHT_MARGIN = 90
CROP_TOP = 192
CROP_BOTTOM_MARGIN = 192
ZOOM_FACTOR = 1.15
COLOR_TOLERANCE = 30

# --- CSS Injection (Timeform) ---
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

# --- Generator ---
UPDATE_INTERVAL_MINUTES = 1

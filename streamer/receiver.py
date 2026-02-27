"""
Tijdvorm Stream Receiver

Lightweight MJPEG stream display client for Raspberry Pi.
Connects to the backend's MJPEG stream and renders frames fullscreen
using Pygame/SDL2 (can run without X server via KMS/DRM).

Usage:
    STREAM_URL=http://mini.netlob:8000/stream python receiver.py
"""

import io
import logging
import os
import signal
import sys
import time

import pygame
import requests
from PIL import Image

from config import (
    BG_COLOR,
    READ_CHUNK_SIZE,
    RECONNECT_DELAY,
    RECONNECT_MAX_DELAY,
    ROTATION,
    STREAM_URL,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("receiver")


class MJPEGReceiver:
    """Connects to an MJPEG stream and yields JPEG frames."""

    def __init__(self, url: str):
        self.url = url
        self.session = requests.Session()

    def frames(self):
        """Yield JPEG frame bytes from the MJPEG stream."""
        response = self.session.get(self.url, stream=True, timeout=10)
        response.raise_for_status()

        # Parse multipart/x-mixed-replace stream
        # Read data and split on JPEG SOI (0xFFD8) and EOI (0xFFD9) markers
        # This is more robust than parsing multipart headers
        buffer = bytearray()
        in_frame = False

        for chunk in response.iter_content(chunk_size=READ_CHUNK_SIZE):
            buffer.extend(chunk)

            while True:
                if not in_frame:
                    # Look for JPEG SOI marker
                    soi = buffer.find(b"\xff\xd8")
                    if soi == -1:
                        # Keep last byte in case SOI spans chunks
                        if len(buffer) > 1:
                            buffer = buffer[-1:]
                        break
                    # Discard everything before SOI
                    buffer = buffer[soi:]
                    in_frame = True

                # Look for JPEG EOI marker (after the SOI)
                eoi = buffer.find(b"\xff\xd9", 2)
                if eoi == -1:
                    break

                # Extract complete JPEG frame
                frame = bytes(buffer[: eoi + 2])
                buffer = buffer[eoi + 2 :]
                in_frame = False
                yield frame


class Display:
    """Fullscreen Pygame display with rotation support."""

    def __init__(self, rotation: int = 0):
        self.rotation = rotation
        self.screen = None
        self.screen_width = 0
        self.screen_height = 0

    def init(self):
        # Try video drivers in order of preference
        drivers = os.environ.get("SDL_VIDEODRIVER", "").split(",") if os.environ.get("SDL_VIDEODRIVER") else []
        drivers = [d.strip() for d in drivers if d.strip()]
        if not drivers:
            drivers = ["kmsdrm", "fbdev", "x11"]

        initialized = False
        for driver in drivers:
            os.environ["SDL_VIDEODRIVER"] = driver
            logger.info(f"Trying SDL video driver: {driver}")
            pygame.display.init()
            if pygame.display.get_init():
                logger.info(f"Video initialized with driver: {driver}")
                initialized = True
                break
            logger.warning(f"Driver {driver} failed, trying next...")

        if not initialized:
            # Last resort: let SDL pick
            if "SDL_VIDEODRIVER" in os.environ:
                del os.environ["SDL_VIDEODRIVER"]
            pygame.display.init()
            if not pygame.display.get_init():
                raise RuntimeError("Could not initialize any SDL video driver")
            logger.info("Video initialized with SDL default driver")

        pygame.font.init()

        # Get display info and go fullscreen
        info = pygame.display.Info()
        self.screen_width = info.current_w
        self.screen_height = info.current_h

        logger.info(f"Display: {self.screen_width}x{self.screen_height}, rotation: {self.rotation}")

        self.screen = pygame.display.set_mode(
            (self.screen_width, self.screen_height),
            pygame.FULLSCREEN | pygame.NOFRAME,
        )
        pygame.display.set_caption("Tijdvorm")
        pygame.mouse.set_visible(False)
        self.clear()

    def clear(self):
        self.screen.fill(BG_COLOR)
        pygame.display.flip()

    def show_frame(self, jpeg_bytes: bytes):
        """Decode JPEG, apply rotation, scale to fit screen, and display."""
        try:
            img = Image.open(io.BytesIO(jpeg_bytes))
        except Exception as e:
            logger.warning(f"Failed to decode frame: {e}")
            return

        # Apply rotation if needed
        if self.rotation == 90:
            img = img.transpose(Image.Transpose.ROTATE_90)
        elif self.rotation == 180:
            img = img.transpose(Image.Transpose.ROTATE_180)
        elif self.rotation == 270:
            img = img.transpose(Image.Transpose.ROTATE_270)

        # Scale to fill screen while maintaining aspect ratio
        img_w, img_h = img.size
        scale_w = self.screen_width / img_w
        scale_h = self.screen_height / img_h
        scale = max(scale_w, scale_h)  # Fill (crop edges if needed)

        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Center on screen (crop overflow)
        x_offset = (self.screen_width - new_w) // 2
        y_offset = (self.screen_height - new_h) // 2

        # Convert PIL image to Pygame surface
        if img.mode != "RGB":
            img = img.convert("RGB")
        surface = pygame.image.fromstring(img.tobytes(), img.size, "RGB")

        self.screen.fill(BG_COLOR)
        self.screen.blit(surface, (x_offset, y_offset))
        pygame.display.flip()

    def process_events(self) -> bool:
        """Process Pygame events. Returns False if should quit."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False
        return True

    def quit(self):
        pygame.quit()


def run():
    logger.info(f"Tijdvorm Stream Receiver")
    logger.info(f"Stream URL: {STREAM_URL}")
    logger.info(f"Rotation: {ROTATION}")

    display = Display(rotation=ROTATION)
    display.init()

    running = True

    def handle_signal(sig, frame):
        nonlocal running
        logger.info(f"Received signal {sig}, shutting down...")
        running = False

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    reconnect_delay = RECONNECT_DELAY

    while running:
        try:
            logger.info(f"Connecting to stream: {STREAM_URL}")
            receiver = MJPEGReceiver(STREAM_URL)

            for jpeg_bytes in receiver.frames():
                if not running:
                    break

                if not display.process_events():
                    running = False
                    break

                display.show_frame(jpeg_bytes)

                # Reset reconnect delay on successful frame
                reconnect_delay = RECONNECT_DELAY

        except requests.ConnectionError:
            logger.warning(f"Connection failed. Retrying in {reconnect_delay:.1f}s...")
        except requests.Timeout:
            logger.warning(f"Connection timed out. Retrying in {reconnect_delay:.1f}s...")
        except Exception as e:
            logger.error(f"Stream error: {e}. Retrying in {reconnect_delay:.1f}s...")

        if running:
            # Exponential backoff
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 1.5, RECONNECT_MAX_DELAY)

            # Keep processing events during reconnect
            if not display.process_events():
                break

    display.quit()
    logger.info("Receiver stopped.")


if __name__ == "__main__":
    run()

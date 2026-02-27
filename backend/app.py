"""FastAPI application — single process entry point for tijdvorm."""

import asyncio
import logging
import os

import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import EASTER_EGGS_DIR, LIVE_DIR, DATA_DIR
from backend.stream import FrameBuffer, router as stream_router
from backend.routes.api import router as api_router, egg_router
from backend.routes.webhooks import router as webhooks_router
from backend.integrations import home_assistant, weather
from backend.generator import generation_loop
import backend.stream as stream_mod

logger = logging.getLogger("tijdvorm")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # Ensure data directories exist
    os.makedirs(EASTER_EGGS_DIR, exist_ok=True)
    os.makedirs(LIVE_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    # Create shared httpx client
    http_client = httpx.AsyncClient()
    home_assistant.set_client(http_client)
    weather.set_client(http_client)

    # Create FrameBuffer
    fb = FrameBuffer()
    stream_mod.frame_buffer = fb

    # Start generation loop
    gen_task = asyncio.create_task(generation_loop(fb))
    logger.info("App started")

    yield

    # Shutdown
    gen_task.cancel()
    try:
        await gen_task
    except asyncio.CancelledError:
        pass
    await http_client.aclose()
    logger.info("App stopped")


app = FastAPI(title="tijdvorm", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes
app.include_router(stream_router)
app.include_router(api_router)
app.include_router(webhooks_router)
app.include_router(egg_router)

# Static files (ensure dirs exist before mounting)
os.makedirs(LIVE_DIR, exist_ok=True)
app.mount("/live", StaticFiles(directory=LIVE_DIR), name="live")


# Configure logging on import
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
# Suppress noisy per-request httpx logs (2 requests/sec from HA polling)
logging.getLogger("httpx").setLevel(logging.WARNING)

"""Weather API integration — async via httpx."""

import logging

import httpx

logger = logging.getLogger("tijdvorm.weather")

_client: httpx.AsyncClient | None = None


def set_client(client: httpx.AsyncClient):
    global _client
    _client = client


async def get_weather_data(url: str) -> dict | None:
    """Fetch weather data JSON from the specified URL."""
    if not _client:
        return None
    try:
        resp = await _client.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"Weather fetch failed: {e}")
        return None

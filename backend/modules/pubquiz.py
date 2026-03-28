"""Pubquiz scoreboard display — persistent browser for live Socket.IO updates.

Keeps a Playwright browser open so the page stays connected via Socket.IO.
Screenshots are taken every second (cheap) without re-navigating.
"""

import asyncio
import logging

from playwright.async_api import async_playwright, Browser, Page, Playwright

from backend.config import OUTPUT_WIDTH, OUTPUT_HEIGHT

logger = logging.getLogger("tijdvorm.pubquiz")

PUBQUIZ_URL = "http://macbroek.swipefy.dev/#scoreboard"

_pw: Playwright | None = None
_browser: Browser | None = None
_page: Page | None = None


async def ensure_browser() -> Page | None:
    """Launch browser and navigate to the pubquiz page if not already open."""
    global _pw, _browser, _page

    if _page is not None:
        try:
            await _page.title()
            return _page
        except Exception:
            logger.warning("Pubquiz page stale, reopening")
            await close_browser()

    logger.info("Launching pubquiz browser...")
    try:
        _pw = await async_playwright().start()
        _browser = await _pw.chromium.launch()
        _page = await _browser.new_page(
            viewport={"width": OUTPUT_WIDTH, "height": OUTPUT_HEIGHT},
        )
        await _page.goto(PUBQUIZ_URL, timeout=30000, wait_until="networkidle")
        logger.info("Pubquiz page loaded")
        return _page
    except Exception as e:
        logger.error(f"Pubquiz browser launch failed: {e}")
        await close_browser()
        return None


async def take_screenshot() -> bytes | None:
    """Take a screenshot of the already-open pubquiz page."""
    page = await ensure_browser()
    if not page:
        return None
    try:
        return await page.screenshot()
    except Exception as e:
        logger.error(f"Pubquiz screenshot failed: {e}")
        await close_browser()
        return None


async def close_browser():
    """Shut down the persistent browser."""
    global _pw, _browser, _page

    if _browser:
        try:
            await _browser.close()
        except Exception:
            pass
    if _pw:
        try:
            await _pw.stop()
        except Exception:
            pass
    _pw = None
    _browser = None
    _page = None
    logger.info("Pubquiz browser closed")

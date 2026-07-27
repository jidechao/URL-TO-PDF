from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from playwright.async_api import Browser, async_playwright

# Minimal stealth: remove the webdriver flag. Realistic UA + viewport set per context.
_STEALTH_JS = "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
# Desktop viewport. Faithful PDFs size the paper to this width (see
# pdf.faithful_pdf), so this is also the PDF's layout width — it must stay
# above common responsive breakpoints (>=1024) to avoid mobile layouts.
_DEFAULT_VIEWPORT = {"width": 1920, "height": 1080}


class BrowserPool:
    """Reuses a single browser; each call gets an isolated context.

    Browser launch is the expensive part, so we keep it around. Each request
    gets a fresh context so cookies/localStorage never leak across users.
    """

    def __init__(self) -> None:
        self._pw = None
        self._browser: Browser | None = None
        self._lock = asyncio.Lock()

    async def launch(self) -> Browser:
        if self._browser is not None:
            return self._browser
        async with self._lock:
            if self._browser is None:
                self._pw = await async_playwright().start()
                self._browser = await self._pw.chromium.launch()
        return self._browser

    @asynccontextmanager
    async def page(
        self,
        cookies: list[dict] | None = None,
        *,
        user_agent: str = DEFAULT_UA,
        viewport: dict | None = None,
    ):
        browser = await self.launch()
        context = await browser.new_context(
            user_agent=user_agent,
            viewport=viewport or _DEFAULT_VIEWPORT,
        )
        await context.add_init_script(_STEALTH_JS)
        if cookies:
            await context.add_cookies(cookies)
        page = await context.new_page()
        try:
            yield page
        finally:
            await context.close()

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None


# Shared default pool for the common single-process case.
_default_pool = BrowserPool()

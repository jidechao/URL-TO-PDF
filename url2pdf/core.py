from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from .browser import BrowserPool, _default_pool
from .extract import extract_article, looks_like_article
from .pdf import (
    build_clean_html,
    clean_pdf,
    faithful_pdf,
    screenshot_pdf,
)
from .render import (
    BLOCK_PRINT_HANDLERS_JS,
    auto_scroll,
    expand_shadow_dom,
    wait_for_dom_stable,
    wait_for_optional_libs,
    wait_for_resources,
)

log = logging.getLogger("url2pdf")

# Below this byte size a PDF is treated as failed rendering (blank Canvas etc.)
# and we fall back to a screenshot PDF.
EMPTY_PDF_THRESHOLD = 5000


async def convert(
    url: str,
    mode: str = "auto",
    cookies: list[dict] | None = None,
    hide_noise: bool = False,
    output_path: str | None = None,
    timeout_ms: int = 30000,
    pool: BrowserPool | None = None,
) -> bytes:
    """Render a URL to PDF bytes.

    mode: "faithful" (as-seen), "clean" (extracted+restyled), or "auto"
    (heuristic pick). hide_noise only affects faithful. output_path writes a
    file in addition to returning bytes.
    """
    if mode not in ("faithful", "clean", "auto"):
        raise ValueError(f"mode must be faithful/clean/auto, got {mode!r}")

    pool = pool or _default_pool
    async with pool.page(cookies=cookies) as page:
        # Must run before page scripts: sites like gov.cn restructure the DOM
        # on beforeprint (squashed header, cloned content, fixed widths that
        # clip at A4). Installed unconditionally — "auto" only resolves to
        # faithful/clean after load, too late for an init script.
        await page.add_init_script(BLOCK_PRINT_HANDLERS_JS)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception as e:
            raise RuntimeError(f"页面加载失败: {e}") from e

        # load state is best-effort: long-poll/SSE pages may never reach it.
        try:
            await page.wait_for_load_state("load", timeout=timeout_ms)
        except Exception:
            pass

        await wait_for_dom_stable(page, timeout_ms=min(timeout_ms, 15000))
        await auto_scroll(page)
        # Return to the top: scroll-triggered sticky headers (class-toggled,
        # e.g. shanghai.gov.cn's stickUp-Nav) revert to their natural in-flow
        # position, so page 1 prints like the browser's first view instead of
        # a fixed bar overlaying the site header.
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(0.5)
        await wait_for_optional_libs(page)
        await wait_for_resources(page)

        actual = mode
        if mode == "auto":
            rendered = await page.content()
            actual = "clean" if looks_like_article(rendered) else "faithful"
            log.info("auto -> %s", actual)

        if actual == "clean":
            rendered = await expand_shadow_dom(page)
            article = extract_article(rendered)
            if article is None:
                log.info("clean extraction failed, falling back to faithful")
                actual = "faithful"
            else:
                full_html = build_clean_html(article, base_url=url)
                pdf = await clean_pdf(page, full_html)

        if actual == "faithful":
            pdf = await faithful_pdf(page, hide_noise=hide_noise)

        if len(pdf) < EMPTY_PDF_THRESHOLD:
            log.info("PDF too small (likely Canvas/WebGL), screenshot fallback")
            pdf = await screenshot_pdf(page)

    if output_path:
        Path(output_path).write_bytes(pdf)
    return pdf

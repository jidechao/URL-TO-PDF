from __future__ import annotations

import asyncio

from playwright.async_api import Page

# Faithful capture must look like the screen, not the site's own print flow.
# Sites (e.g. gov.cn) bind beforeprint and restructure the DOM for printing:
# squashed headers, cloned content, fixed pixel widths that clip at A4. Since
# page.pdf() fires beforeprint, swallow the event before page scripts can
# register handlers. Installed via add_init_script (runs before page scripts);
# beforeprint/afterprint target window, where listeners fire in registration
# order, so ours runs first and stopImmediatePropagation blocks theirs.
BLOCK_PRINT_HANDLERS_JS = """
for (const type of ['beforeprint', 'afterprint']) {
  window.addEventListener(type, (e) => e.stopImmediatePropagation(), true);
}
"""

# Hard caps for infinite scroll. Social feeds never stop; without these we'd
# OOM or produce a multi-thousand-page PDF. Any one tripping stops the loop.
MAX_SCROLL_ROUNDS = 50
MAX_DOM_NODES = 5000
MAX_DOC_HEIGHT = 50000


async def wait_for_dom_stable(
    page: Page, *, stable_ms: int = 2000, timeout_ms: int = 15000
) -> None:
    """Wait until the DOM stops mutating (Ajax/SPA settled).

    networkidle is unreliable when a page has polling, analytics, SSE, or
    websockets. MutationObserver catches real settlement instead.
    """
    await page.evaluate(
        """([stableMs, timeoutMs]) => new Promise((resolve) => {
            const obs = new MutationObserver(() => {
                clearTimeout(timer);
                timer = setTimeout(() => { obs.disconnect(); resolve(); }, stableMs);
            });
            let timer = setTimeout(() => { obs.disconnect(); resolve(); }, stableMs);
            obs.observe(document.body, {childList: true, subtree: true, attributes: true});
            setTimeout(() => { obs.disconnect(); resolve(); }, timeoutMs);
        })""",
        [stable_ms, timeout_ms],
    )


async def auto_scroll(page: Page, *, max_rounds: int = MAX_SCROLL_ROUNDS) -> None:
    """Scroll to the bottom to trigger lazy-loaded content.

    Stops when the page height stops changing OR any of three hard caps hit
    (scroll rounds, DOM node count, document height).
    """
    last_height = 0
    for _ in range(max_rounds):
        height = await page.evaluate("document.body.scrollHeight")
        node_count = await page.evaluate("document.getElementsByTagName('*').length")
        if height >= MAX_DOC_HEIGHT or node_count >= MAX_DOM_NODES:
            break
        if height == last_height:
            break
        last_height = height
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        try:
            await page.wait_for_load_state("load", timeout=3000)
        except Exception:
            pass
        await asyncio.sleep(0.8)


async def wait_for_resources(page: Page, *, timeout_ms: int = 10000) -> None:
    """Wait for fonts loaded + all images decoded.

    Without this, page.pdf() after setContent frequently emits blank image
    boxes and fallback fonts.
    """
    try:
        await page.wait_for_function(
            "() => !document.fonts || document.fonts.status === 'loaded'",
            timeout=timeout_ms,
        )
    except Exception:
        pass
    try:
        await page.wait_for_function(
            "() => [...document.images].every(img => img.complete)",
            timeout=timeout_ms,
        )
    except Exception:
        pass


async def wait_for_optional_libs(page: Page, *, timeout_ms: int = 5000) -> None:
    """Feature-detect and trigger MathJax/Mermaid global entrypoints.

    Only fires if the site exposed them as globals (not the ESM/React case).
    Never hard-waits: a site without these resolves immediately.
    """
    try:
        await page.evaluate(
            """async () => {
                try {
                    if (window.MathJax && MathJax.typesetPromise) {
                        await MathJax.typesetPromise();
                    }
                } catch (e) {}
                try {
                    if (window.mermaid && mermaid.run) {
                        await mermaid.run();
                    }
                } catch (e) {}
            }"""
        )
    except Exception:
        pass


async def expand_shadow_dom(page: Page) -> str:
    """Inline shadow DOM content into the light DOM, returning the full HTML.

    Required for clean-mode extraction: Readability/trafilatura parse an HTML
    string and cannot see shadow content otherwise. Styles inside the shadow
    root (<style> nodes) are cloned along with the content so they survive the
    move. adoptedStyleSheets are a known gap (constructable stylesheets have no
    extractable text); best-effort, sufficient for article text.
    """
    return await page.evaluate(
        """() => {
            const expand = (root) => {
                if (!root) return;
                for (const el of root.querySelectorAll('*')) {
                    if (el.shadowRoot) {
                        for (const node of [...el.shadowRoot.childNodes]) {
                            el.appendChild(node.cloneNode(true));
                        }
                        expand(el);
                    }
                }
            };
            expand(document);
            return document.documentElement.outerHTML;
        }"""
    )

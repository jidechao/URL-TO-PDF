from __future__ import annotations

import asyncio
import base64
import html as html_mod

from playwright.async_api import Page

from .render import wait_for_resources

PDF_MARGINS = {"top": "15mm", "bottom": "15mm", "left": "15mm", "right": "15mm"}

# High-confidence noise only: cookie/consent banners. Display:none keeps DOM
# intact (no node deletion), so layout stays stable for faithful capture.
NOISE_HIDE_CSS = """
#onetrust-banner-sdk,
[id*="cookie-banner" i], [id*="cookieBanner" i],
.cc-banner, .cookie-banner, .cookie-consent, .cookies-banner,
#cmp-wrapper, .gdpr-banner,
[class*="CookieConsent" i], [class*="cookieConsent" i] { display: none !important; }
"""

# Unified Print CSS for clean mode: article-grade typography, A4-safe layout.
PRINT_CSS = """
@page { margin: 15mm 15mm; }
* { box-sizing: border-box; }
body {
  max-width: 820px;
  margin: 0 auto;
  padding: 0 8px;
  font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei",
               "Source Han Sans SC", "Helvetica Neue", Arial, sans-serif;
  font-size: 15px;
  line-height: 1.8;
  color: #1a1a1a;
  word-wrap: break-word;
}
h1 { font-size: 28px; line-height: 1.3; margin: 0 0 16px; }
h2 { font-size: 22px; margin: 28px 0 12px; }
h3 { font-size: 18px; margin: 24px 0 10px; }
p { margin: 0 0 16px; }
img { max-width: 100%; height: auto; display: block; margin: 16px auto; }
pre {
  background: #f6f8fa; padding: 12px 14px; border-radius: 6px;
  overflow-x: auto; font-size: 13px; line-height: 1.5;
  white-space: pre-wrap; word-break: break-word;
}
code { font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace; }
p code, li code { background: #f6f8fa; padding: 1px 5px; border-radius: 4px; font-size: 13px; }
blockquote {
  border-left: 4px solid #d0d7de; margin: 16px 0; padding: 4px 16px;
  color: #57606a; background: #f6f8fa;
}
table { border-collapse: collapse; width: 100%; margin: 16px 0; font-size: 14px; }
th, td { border: 1px solid #d0d7de; padding: 8px 10px; text-align: left; }
th { background: #f6f8fa; }
a { color: #0969da; text-decoration: none; word-break: break-all; }
hr { border: none; border-top: 1px solid #d0d7de; margin: 24px 0; }
h1, h2, h3 { break-after: avoid; }
pre, table, img { break-inside: avoid; }
"""


async def faithful_pdf(page: Page, *, hide_noise: bool = False) -> bytes:
    """Print the page as-seen. Screen media avoids sites' @media print that
    would otherwise hide or reflow content."""
    await page.emulate_media(media="screen")
    if hide_noise:
        await page.add_style_tag(content=NOISE_HIDE_CSS)
        await asyncio.sleep(0.3)
    # Chromium repeats position:fixed elements at the same spot on EVERY
    # printed page, overlaying content. Convert survivors (fixed regardless
    # of scroll position, e.g. always-fixed headers) to absolute: they print
    # once, where the screen shows them. Visibility is untouched.
    await page.evaluate(
        """() => {
            for (const el of document.querySelectorAll('body *')) {
                if (getComputedStyle(el).position === 'fixed') {
                    el.style.setProperty('position', 'absolute', 'important');
                }
            }
        }"""
    )
    # Chromium lays out page.pdf() at the PAPER width, not the viewport width.
    # A4 (210mm - margins ≈ 680px) falls below the 768px responsive breakpoint,
    # so sites render their mobile layout (collapsing nav bars, stacking
    # columns). Size the paper to the viewport width instead, keeping A4's
    # 210:297 aspect ratio, so the layout viewport is genuinely desktop.
    vp = page.viewport_size or {"width": 1280, "height": 900}
    width_px = vp["width"]
    height_px = round(width_px * 297 / 210)
    return await page.pdf(
        width=f"{width_px}px",
        height=f"{height_px}px",
        print_background=True,
        margin=PDF_MARGINS,
    )


async def clean_pdf(page: Page, full_html: str) -> bytes:
    """Re-render cleaned HTML to PDF. setContent + resource-ready gate
    prevents blank images / fallback fonts in the output."""
    await page.set_content(full_html, wait_until="load")
    await page.emulate_media(media="screen")
    await wait_for_resources(page)
    return await page.pdf(format="A4", print_background=True, margin=PDF_MARGINS)


async def screenshot_pdf(page: Page) -> bytes:
    """Fallback for Canvas/WebGL/heavy-SVG pages that vectorize poorly: a
    full-page screenshot wrapped back into a PDF. Loses selectable text but
    preserves fidelity."""
    img = await page.screenshot(full_page=True, type="png")
    b64 = base64.b64encode(img).decode()
    wrapper = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>@page{margin:0}body{margin:0}img{width:100%}</style></head>"
        f"<body><img src='data:image/png;base64,{b64}'></body></html>"
    )
    await page.set_content(wrapper, wait_until="load")
    await page.emulate_media(media="screen")
    return await page.pdf(
        format="A4",
        print_background=True,
        margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
    )


def build_clean_html(article: dict, base_url: str = "") -> str:
    """Wrap extracted article in the unified Print-CSS document.

    The <base> tag is critical: setContent resets the document URL to
    about:blank, which would break relative image/css paths. Base restores
    resolution against the original URL.

    Title dedup: trafilatura/readability body_html already contains the title
    as the first heading (<h1>/<h2>). We only prepend an <h1> when the title
    text is NOT present in the body's leading window, otherwise we'd render it
    twice.
    """
    title = html_mod.escape(article.get("title") or "", quote=True)
    base = f'<base href="{html_mod.escape(base_url, quote=True)}">' if base_url else ""
    body = article.get("body_html") or ""
    # Dedup: trafilatura/readability body_html already starts with the title
    # as a heading element. Only prepend <h1> when the raw title text is absent
    # from the body's leading window. +100 tolerates wrapper tags (<h2>, <header>).
    raw_title = article.get("title") or ""
    need_h1 = bool(raw_title) and raw_title not in body[:len(raw_title) + 100]
    head = f"<h1>{title}</h1>" if need_h1 else ""
    return (
        f'<!doctype html><html lang="zh"><head><meta charset="utf-8">{base}'
        f"<style>{PRINT_CSS}</style></head><body>{head}{body}</body></html>"
    )

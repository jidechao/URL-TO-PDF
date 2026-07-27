import asyncio
from pathlib import Path

import pytest

from url2pdf import convert
from url2pdf.browser import BrowserPool
from url2pdf.extract import extract_article, looks_like_article
from url2pdf.pdf import build_clean_html
from url2pdf.render import BLOCK_PRINT_HANDLERS_JS

FIX = Path(__file__).parent / "fixtures"
ARTICLE_URL = (FIX / "article.html").as_uri()
LANDING_URL = (FIX / "landing.html").as_uri()
PRINTTRAP_URL = (FIX / "printtrap.html").as_uri()

# All end-to-end tests share one browser on one loop. asyncio.run would make a
# fresh loop per test and break browser reuse (playwright futures bind to a loop).
_POOL = BrowserPool()
_LOOP = asyncio.new_event_loop()


def _run(coro):
    return _LOOP.run_until_complete(coro)


# --- pure-function unit tests (no browser) ---

def test_looks_like_article_true():
    html = (FIX / "article.html").read_text(encoding="utf-8")
    assert looks_like_article(html) is True


def test_looks_like_article_false():
    html = (FIX / "landing.html").read_text(encoding="utf-8")
    assert looks_like_article(html) is False


def test_extract_article_returns_content():
    html = (FIX / "article.html").read_text(encoding="utf-8")
    res = extract_article(html)
    assert res is not None
    assert "一致性" in res["body_html"]
    assert len(res["body_html"]) > 500


def test_build_clean_html_injects_base():
    art = {"title": "T & <b>", "body_html": "<p>x</p>"}
    html = build_clean_html(art, base_url="https://example.com/a/")
    assert '<base href="https://example.com/a/">' in html
    assert "<h1>T &amp; &lt;b&gt;</h1>" in html


# --- end-to-end pipeline (browser) ---

@pytest.mark.parametrize("mode", ["faithful", "clean", "auto"])
def test_convert_article_modes(mode):
    pdf = _run(convert(ARTICLE_URL, mode=mode, pool=_POOL))
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 5000


def test_convert_landing_auto():
    pdf = _run(convert(LANDING_URL, mode="auto", pool=_POOL))
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 5000


def test_convert_invalid_mode():
    with pytest.raises(ValueError):
        _run(convert(ARTICLE_URL, mode="bogus", pool=_POOL))


def test_block_print_handlers_js_prevents_dom_mangling():
    """gov.cn-style beforeprint handlers must not run during page.pdf().

    The init script installs a capture listener before page scripts register
    theirs; stopImmediatePropagation then keeps the DOM in its screen state.
    """

    async def _t():
        async with _POOL.page() as page:
            await page.add_init_script(BLOCK_PRINT_HANDLERS_JS)
            await page.goto(PRINTTRAP_URL)
            # Chromium fires this during printToPDF; dispatch manually here.
            await page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
            fired = await page.evaluate("window.__beforeprintFired")
            visible = await page.evaluate(
                "getComputedStyle(document.getElementById('content')).display"
            )
            return fired, visible

    fired, visible = _run(_t())
    assert fired is False
    assert visible != "none"

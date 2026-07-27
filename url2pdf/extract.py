from __future__ import annotations

import json

import trafilatura
from readability import Document

# auto-mode threshold: extracted plain text this long (chars) => treat as article.
ARTICLE_TEXT_THRESHOLD = 800


def extract_article(html: str) -> dict | None:
    """Extract article body HTML.

    Primary: trafilatura (more robust on diverse pages). Fallback:
    readability-lxml. Returns {"title", "body_html", "source"} or None.
    """
    res = _trafilatura(html)
    if res and res["body_html"]:
        res["source"] = "trafilatura"
        return res
    res = _readability(html)
    if res and res["body_html"]:
        res["source"] = "readability"
        return res
    return None


def _trafilatura(html: str) -> dict | None:
    try:
        body = trafilatura.extract(
            html,
            output_format="html",
            include_images=True,
            include_links=True,
            include_tables=True,
        )
        if not body:
            return None
        title = None
        meta = trafilatura.extract(html, output_format="json", with_metadata=True)
        if meta:
            try:
                title = json.loads(meta).get("title")
            except Exception:
                pass
        return {"title": title, "body_html": body}
    except Exception:
        return None


def _readability(html: str) -> dict | None:
    try:
        doc = Document(html)
        return {"title": doc.title(), "body_html": doc.summary(html_partial=False)}
    except Exception:
        return None


def looks_like_article(html: str) -> bool:
    """Heuristic for auto mode: is there enough extractable text to bother
    with the clean pipeline?"""
    try:
        text = trafilatura.extract(html, output_format="txt") or ""
    except Exception:
        text = ""
    return len(text.strip()) >= ARTICLE_TEXT_THRESHOLD

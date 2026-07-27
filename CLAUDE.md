# URL2PDF — Project Guide for Claude

Deep design detail (read on demand, don't duplicate here): @URL2MARKDOWN.md

## Project Overview

URL2PDF is a Python CLI/library that converts URLs to PDF. It handles modern JavaScript-rendered pages (React, Vue, Next.js, etc.) and supports three rendering modes:

- **`faithful`** — WYSIWYG snapshot; preserves original layout, styles, and colors. Paper width matches the desktop viewport so responsive sites stay in desktop layout.
- **`clean`** — Extracts article content, removes navigation/ads/comments/noise, and applies a unified print stylesheet.
- **`auto`** (default) — Heuristic pick: uses `trafilatura` to test whether the page has enough article-like text (≥800 chars); if so, uses `clean`, otherwise `faithful`.

The project is intentionally small and focused. It is not a service (HTTP API is listed as a known limitation), and the browser pool is currently single-process/browser.

## Architecture

```text
url2pdf/
├── __init__.py     # Public API: convert()
├── __main__.py     # CLI entry point
├── core.py         # convert() orchestration
├── browser.py      # BrowserPool (reused Chromium, fresh context per call)
├── render.py       # DOM stability, auto-scroll, resource waits, shadow DOM, beforeprint blocker
├── extract.py      # Article extraction (trafilatura → readability-lxml fallback)
└── pdf.py          # faithful / clean / screenshot-fallback PDF generation + Print CSS
```

### Data flow

1. Launch/reuse Chromium via `BrowserPool`.
2. Inject init script to block `beforeprint`/`afterprint` handlers before page scripts run.
3. `page.goto(url, wait_until="domcontentloaded")`, best-effort `load`.
4. Wait for DOM stability via `MutationObserver`.
5. Auto-scroll to trigger lazy loading (with hard caps for infinite scroll).
6. Scroll back to top so sticky headers return to document flow.
7. Wait for MathJax/Mermaid (if present) and fonts/images.
8. Resolve `auto` mode; for `clean`, expand shadow DOM and extract article.
9. Render PDF; if output is < 5 KB, fall back to full-page screenshot PDF.

## Tech Stack

- **Language**: Python ≥ 3.10
- **Build backend**: hatchling
- **Package manager**: pip
- **Browser automation**: Playwright + Chromium
- **Content extraction**: trafilatura, readability-lxml, lxml

## Setup

```bash
git clone https://github.com/jidechao/URL-TO-PDF.git URL2PDF
cd URL2PDF
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate
pip install -e .
playwright install chromium
```

## Common Commands

```bash
# Run tests
.venv\Scripts\python.exe -m pytest tests/ -v

# CLI usage
python -m url2pdf https://example.com -o output.pdf
python -m url2pdf https://example.com --mode clean -o article.pdf
python -m url2pdf https://example.com --mode faithful --hide-noise -o snapshot.pdf
python -m url2pdf https://example.com/private --cookies '[{"name":"session","value":"xxx","url":"https://example.com"}]'

# Library usage
import asyncio
from url2pdf import convert

async def main():
    pdf = await convert("https://example.com", mode="auto", output_path="output.pdf")

asyncio.run(main())
```

## Code Style

- Follow PEP 8.
- Use type annotations on function signatures.
- Use `from __future__ import annotations`.
- Prefer `snake_case`.
- Use the `logging` module; avoid `print()` in library code.
- Keep changes surgical: match existing quote style and formatting within a file; do not mass-reformat unrelated code.
- Lint with `ruff check`; the rule set is pinned in `pyproject.toml` (E4/E7/E9/F) so results don't depend on the installed ruff version. The broad `except Exception` boundaries around third-party HTML parsers and best-effort page waits are deliberate — don't "fix" them to satisfy stricter rules.

## Important Implementation Details

### Viewport and paper width
The default viewport is 1920×1080. In `faithful` mode, the PDF paper is sized to the viewport width (keeping A4's 210:297 aspect ratio) so pages do not collapse into mobile layouts at print time.

### Sticky / fixed elements
After auto-scrolling, the page is scrolled back to the top so scroll-toggled sticky headers return to their natural position. Immediately before printing, any `position: fixed` elements are converted to `position: absolute` so Chromium does not repeat them on every printed page.

### `beforeprint` event blocking
Some sites (e.g., gov.cn) restructure the DOM inside `beforeprint` handlers, causing duplicate or clipped output. The `BLOCK_PRINT_HANDLERS_JS` init script is added before page scripts run and stops immediate propagation of `beforeprint`/`afterprint`.

### Blank PDF fallback
If the generated PDF is smaller than 5 KB, the pipeline assumes a Canvas/WebGL/SVG rendering failure and falls back to a full-page screenshot wrapped in a PDF. This fallback preserves visual fidelity but produces rasterized, non-selectable text.

### Auto-scroll safety caps
Infinite-scroll pages are bounded by:
- max 50 scroll rounds
- max 5000 DOM nodes
- max 50 000 px document height

### Shadow DOM
`clean` mode expands shadow DOM content into the light DOM before extraction. Styles inside the shadow root are cloned, but `adoptedStyleSheets` (constructable stylesheets) cannot be extracted and are a known gap.

### Clean-mode base URL
`build_clean_html` injects a `<base href="...">` tag because `page.set_content()` resets the document URL to `about:blank`, which would break relative image/CSS paths.

### Title deduplication
If the extracted title text already appears in the leading portion of `body_html`, no extra `<h1>` is prepended, avoiding duplicate titles.

## Testing

- Tests are in `tests/test_pipeline.py`.
- Unit tests cover `looks_like_article`, `extract_article`, and `build_clean_html` without a browser.
- End-to-end tests share one `BrowserPool` and one manually managed event loop to avoid `asyncio.run` creating a fresh loop per test.
- Fixtures live in `tests/fixtures/` (`article.html`, `landing.html`, `printtrap.html`).

## Dependencies

Runtime dependencies are in `pyproject.toml` and `requirements.txt`:

```text
playwright>=1.40.0
trafilatura>=1.6.0
readability-lxml>=0.8.0
lxml>=4.9.0
```

Dev dependencies (lint + test): `pip install -e .[dev]` installs `pytest` and `ruff`.

## Known Limitations

- `adoptedStyleSheets` cannot be extracted for shadow DOM.
- Complex Cloudflare/Akamai challenge pages may block the minimal stealth setup.
- Screenshot-fallback PDFs are rasterized and not text-selectable.
- No HTTP service interface; only CLI and library APIs.
- Single browser/process pool; not yet designed for high-concurrency server use.

## AI Coding Guidance

- Read the existing module before adding code. The pipeline is deliberately sequential; changes to order (e.g., moving `beforeprint` blocking, scroll timing, or resource waits) can break output quality.
- Do not add new dependencies silently. Prefer standard library or what's already installed. If a dependency is necessary, explain why and update both `pyproject.toml` and `requirements.txt`.
- Write tests for new behavior. Keep browser-dependent tests in the existing shared-pool pattern.
- When modifying PDF output, test against both `faithful` and `clean` modes and at least one fixture.
- Avoid premature abstraction. The current architecture is flat and function-oriented; do not introduce classes/frameworks unless the requirement genuinely needs them.
- Keep surgical diffs; do not mass-reformat files you are not otherwise changing.

## Coding Rules

Condensed from `AGENTS-RULES.md`. **This file is the single source of truth — on any conflict, CLAUDE.md wins.**

- **Read before you write.** Read the files you're modifying and the existing patterns before generating code. If no pattern exists for what you need, ask — don't guess.
- **Think before you code.** State assumptions, name tradeoffs, and if multiple approaches exist present 2–3 with a recommendation. If something is confusing, stop and ask instead of filling gaps with plausible code.
- **Simplicity.** Write the minimum code that solves this problem now. No premature abstraction, speculative error handling, or "in case we need it" configurability. Duplication is cheaper than the wrong abstraction.
- **Surgical changes.** Every changed line must connect directly to the task. Match the file's existing style over personal preference. Clean up only what your own change made dead.
- **Verify, don't assume.** For bug fixes, write a failing reproduction test first, then fix. Run the existing suite before and after your change; report pre-existing failures instead of ignoring them. Test behavior, not implementation. A task isn't done until verification passes.
- **Goal-driven execution.** Turn vague tasks into verifiable success criteria before starting; for multi-step work, state the plan first.
- **Debug by investigating, not guessing.** Read the full error and stack trace. Reproduce first. Change one thing at a time. Fix root causes, not symptoms. If stuck, say what you tried and what you're seeing.
- **Dependencies are costly.** Prefer the existing stack and standard library; check that any new package is maintained and proportionate. Say why when adding one.
- **Communicate.** Say what you did and why, flag concerns proactively, and be precise about uncertainty. Write specific commit messages.
- **Avoid the classic failure modes:** kitchen-sink scope creep, wrong abstraction, invisible architectural decisions, happy-path-only code, hallucinated APIs, style drift, runaway refactors.

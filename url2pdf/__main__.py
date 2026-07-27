from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .core import convert


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="url2pdf",
        description="URL to PDF (faithful / clean / auto) with JS rendering",
    )
    ap.add_argument("url", help="target URL")
    ap.add_argument("-o", "--output", default="output.pdf", help="output PDF path")
    ap.add_argument(
        "--mode",
        choices=["faithful", "clean", "auto"],
        default="auto",
        help="faithful=as-seen, clean=extracted+restyled, auto=heuristic (default)",
    )
    ap.add_argument(
        "--hide-noise", action="store_true", help="hide cookie/consent banners (faithful only)"
    )
    ap.add_argument(
        "--cookies",
        help='JSON cookie list, e.g. [{"name":"k","value":"v","url":"https://x"}]',
    )
    ap.add_argument("--timeout", type=int, default=30000, help="page timeout in ms")
    args = ap.parse_args(argv)

    cookies = json.loads(args.cookies) if args.cookies else None
    from .browser import _default_pool

    async def _amain():
        try:
            return await convert(
                args.url,
                mode=args.mode,
                cookies=cookies,
                hide_noise=args.hide_noise,
                output_path=args.output,
                timeout_ms=args.timeout,
            )
        finally:
            await _default_pool.close()

    pdf = asyncio.run(_amain())
    print(f"wrote {args.output} ({len(pdf)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

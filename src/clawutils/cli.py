"""Unified CLI entrypoint for clawutils.

For now this is a very small stub that will grow into:

    clawutils web scrape <URL>
    clawutils text patch <FILE> [...]
    clawutils fs prune [...]

The first concrete utility we will implement is a robust web scraper
that outputs normalized markdown suitable for Clawkb ingest.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clawutils",
        description="CLI utilities around OpenClaw (web, text, kb, fs)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Placeholder for the first utility group: web scraping.
    sp_web = sub.add_parser("web", help="Web-related utilities (scrapers, cleaners)")
    sp_web_sub = sp_web.add_subparsers(dest="web_cmd", required=True)

    sp_web_scrape = sp_web_sub.add_parser(
        "scrape",
        help="Scrape a web page and print normalized markdown (stub: to be implemented)",
    )
    sp_web_scrape.add_argument("url", help="URL to scrape")

    args = parser.parse_args(argv)

    if args.command == "web" and args.web_cmd == "scrape":
        # For now we only stub the command so that `clawutils web scrape URL`
        # exists and prints a clear error. The real implementation will live
        # under clawutils.web.* and be wired here.
        sys.stderr.write(
            "ERROR: web scrape not implemented yet. This is a stub CLI; "
            "the actual scraper will be added in a future commit.\n"
        )
        return 2

    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

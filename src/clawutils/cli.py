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
import subprocess
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clawutils",
        description="CLI utilities around OpenClaw (web, text, kb, fs)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Web-related utilities (scrapers, cleaners)
    sp_web = sub.add_parser("web", help="Web-related utilities (scrapers, cleaners)")
    sp_web_sub = sp_web.add_subparsers(dest="web_cmd", required=True)

    sp_web_scrape = sp_web_sub.add_parser(
        "scrape",
        help="Scrape a web page and print normalized markdown",
    )
    sp_web_scrape.add_argument("url", help="URL to scrape")

    # Text utilities (patch/transform)
    sp_text = sub.add_parser("text", help="Text utilities (patch, transform)")
    sp_text_sub = sp_text.add_subparsers(dest="text_cmd", required=True)

    sp_text_patch = sp_text_sub.add_parser(
        "patch",
        help="Patch a text file (prepend/append/after marker)",
    )
    sp_text_patch.add_argument("--file", required=True, help="Target file path")
    sp_text_patch.add_argument("--text", required=True, help="Text to insert")
    sp_text_patch.add_argument(
        "--mode",
        choices=["prepend", "append", "after"],
        required=True,
        help="Patch mode",
    )
    sp_text_patch.add_argument(
        "--marker",
        help="Marker for 'after' mode (required when --mode=after)",
    )

    args = parser.parse_args(argv)

    if args.command == "web" and args.web_cmd == "scrape":
        # Resolve the bundled Node.js scraper script and delegate to `node`.
        script_path = Path(__file__).resolve().parent / "web" / "scrape.js"
        if not script_path.exists():
            sys.stderr.write(
                f"ERROR: scraper script not found at {script_path}. "
                "Check your clawutils installation.\n"
            )
            return 2

        cmd = ["node", str(script_path), args.url]
        try:
            proc = subprocess.run(cmd)
            return proc.returncode
        except FileNotFoundError:
            sys.stderr.write(
                "ERROR: 'node' executable not found. Install Node.js to use "
                "'clawutils web scrape'.\n"
            )
            return 2
        except Exception as e:
            sys.stderr.write(f"ERROR: failed to run scraper: {e}\n")
            return 2

    if args.command == "text" and args.text_cmd == "patch":
        # Delegate to the text patcher module.
        from .text.patch import main as text_patch_main

        return text_patch_main(
            [
                "--file",
                args.file,
                "--text",
                args.text,
                "--mode",
                args.mode,
            ]
            + (["--marker", args.marker] if args.mode == "after" and args.marker else [])
        )

    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

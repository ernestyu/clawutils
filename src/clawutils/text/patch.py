"""Text patching utilities for clawutils.

This module provides a small helper to insert text into an existing file in a
few simple modes:

- prepend: add text at the beginning
- append: add text at the end
- after: insert text immediately after a marker substring

It is intentionally conservative: if the file does not exist, or the marker
is not found, it prints a clear error and exits with a non-zero code.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional


def patch_file(file_path: str, text: str, mode: str, marker: Optional[str] = None) -> None:
    """Patch a file by inserting text according to the given mode.

    Modes:
    - prepend: text + newline + original content
    - append: original content (stripped trailing whitespace) + two newlines + text + newline
    - after: split on the first occurrence of marker and insert text after it
    """
    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    new_content: str
    if mode == "prepend":
        new_content = text + "\n" + content
    elif mode == "append":
        new_content = content.rstrip() + "\n\n" + text + "\n"
    elif mode == "after":
        if not marker:
            print("ERROR: Mode 'after' requires --marker")
            sys.exit(1)
        if marker not in content:
            print(f"ERROR: Marker '{marker}' not found in file")
            sys.exit(1)
        parts = content.split(marker, 1)
        new_content = parts[0] + marker + "\n" + text + parts[1]
    else:
        print(f"ERROR: Unknown mode: {mode}")
        sys.exit(1)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"SUCCESS: Patched {file_path} (Mode: {mode})")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="clawutils text patch",
        description="Precision text patcher for clawutils (prepend/append/after marker)",
    )
    parser.add_argument("--file", required=True, help="Target file path")
    parser.add_argument("--text", required=True, help="Text to insert")
    parser.add_argument(
        "--mode",
        choices=["prepend", "append", "after"],
        required=True,
        help="Patch mode",
    )
    parser.add_argument(
        "--marker",
        help="Marker for 'after' mode (required when --mode=after)",
    )

    args = parser.parse_args(argv)
    patch_file(args.file, args.text, args.mode, args.marker)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

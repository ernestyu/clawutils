"""Utilities for clawutils.

Currently provides:
- load_project_env: load a .env file from the project root without
  overriding existing environment variables.
"""

from __future__ import annotations

from pathlib import Path


def load_project_env(path: Path | None = None) -> None:
    """Load a .env file from the project root using setdefault semantics.

    - If a key is already present in os.environ, it is not overridden.
    - Otherwise, the value from .env is used.
    """

    import os

    if path is None:
        # utils.py -> clawutils/ -> src/ -> repo root
        root = Path(__file__).resolve().parents[2]
        path = root / ".env"

    if not path.exists():
        return

    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
    except Exception:
        # Best-effort; failures here should not break the CLI.
        return

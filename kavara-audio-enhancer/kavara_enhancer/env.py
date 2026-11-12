"""Minimal .env loader (no extra dependency). Real environment variables win."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: Path | None = None) -> bool:
    """Load KEY=VALUE lines from ``.env`` (cwd, then project root) into os.environ."""
    candidates = [path] if path else [Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"]
    for candidate in candidates:
        if candidate and candidate.is_file():
            for raw in candidate.read_text(encoding="utf-8-sig").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip().removeprefix("export ").strip()
                value = value.strip().strip("'\"")
                if key and value:
                    os.environ.setdefault(key, value)
            return True
    return False

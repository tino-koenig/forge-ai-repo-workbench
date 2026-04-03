"""Minimal .env loader for Forge CLI bootstrap."""

from __future__ import annotations

import re
import os
from pathlib import Path


ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _parse_env_line(line: str) -> tuple[str, str] | None:
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return None
    if raw.startswith("export "):
        raw = raw[len("export ") :].strip()
    if "=" not in raw:
        return None
    key, value = raw.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not ENV_KEY_RE.match(key):
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def load_env_file(path: Path) -> int:
    """Load env vars from file without overriding existing process environment."""
    if not path.exists() or not path.is_file():
        return 0
    loaded = 0
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    for line in content.splitlines():
        parsed = _parse_env_line(line)
        if parsed is None:
            continue
        key, value = parsed
        # Existing process env wins over .env content.
        if key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded

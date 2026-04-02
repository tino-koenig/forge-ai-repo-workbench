"""Forge CLI executable module."""

from __future__ import annotations

import sys

from cmd.cli import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
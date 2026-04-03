"""Module entrypoint for `python -m forge` and console script wiring."""

from __future__ import annotations

import sys

from forge_cmd.cli import main as cli_main


def main(argv: list[str] | None = None) -> int:
    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

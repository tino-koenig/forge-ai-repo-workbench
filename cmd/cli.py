"""CLI entrypoint setup for Forge."""

from __future__ import annotations

import argparse

from core.capability_model import build_request
from core.runtime import execute


REQUIRES_PAYLOAD = {
    "query": True,
    "explain": True,
    "review": True,
    "describe": False,
    "test": True,
}

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forge", description="Forge CLI")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root to analyze (default: current directory)",
    )
    subparsers = parser.add_subparsers(dest="capability", required=True)

    query_parser = subparsers.add_parser("query", help="Run query capability")
    query_parser.add_argument(
        "parts",
        nargs="+",
        help="Question; optional profile prefix: simple|standard|detailed",
    )

    explain_parser = subparsers.add_parser("explain", help="Run explain capability")
    explain_parser.add_argument(
        "parts",
        nargs="+",
        help="Target; optional profile prefix: simple|standard|detailed",
    )

    review_parser = subparsers.add_parser("review", help="Run review capability")
    review_parser.add_argument(
        "parts",
        nargs="+",
        help="Target; optional profile prefix: simple|standard|detailed",
    )

    describe_parser = subparsers.add_parser("describe", help="Run describe capability")
    describe_parser.add_argument(
        "parts",
        nargs="*",
        help="Optional target; optional profile prefix: simple|standard|detailed",
    )

    test_parser = subparsers.add_parser("test", help="Run test capability")
    test_parser.add_argument(
        "parts",
        nargs="+",
        help="Target; optional profile prefix: simple|standard|detailed",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    parts = getattr(args, "parts", []) or []
    try:
        request = build_request(
            capability_name=args.capability,
            parts=parts,
            require_payload=REQUIRES_PAYLOAD[args.capability],
        )
    except ValueError as exc:
        parser.error(str(exc))
        return 2
    return execute(request=request, args=args)

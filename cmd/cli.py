"""CLI entrypoint setup for Forge."""

from __future__ import annotations

import argparse
from pathlib import Path

from core.capability_model import build_request
from core.env_loader import load_env_file
from core.runtime import execute


REQUIRES_PAYLOAD = {
    "index": False,
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
    parser.add_argument(
        "--env-file",
        help="Optional .env file path; defaults to <repo-root>/.env when present",
    )
    parser.add_argument(
        "--output-format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--llm-mode",
        choices=("auto", "off", "force"),
        default="auto",
        help="LLM invocation mode (default: auto)",
    )
    parser.add_argument(
        "--llm-provider",
        help="Explicit LLM provider override (or FORGE_LLM_PROVIDER)",
    )
    parser.add_argument(
        "--llm-model",
        help="Explicit LLM model override (or FORGE_LLM_MODEL)",
    )
    parser.add_argument(
        "--llm-base-url",
        help="Explicit OpenAI-compatible base URL override (or FORGE_LLM_BASE_URL)",
    )
    parser.add_argument(
        "--llm-timeout-s",
        type=float,
        help="Explicit LLM timeout in seconds (or FORGE_LLM_TIMEOUT_S)",
    )
    subparsers = parser.add_subparsers(dest="capability", required=True)

    index_parser = subparsers.add_parser("index", help="Build or refresh repository index")
    index_parser.add_argument(
        "parts",
        nargs="*",
        help="Optional operation/profile prefix: simple|standard|detailed",
    )

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
    repo_root = Path(args.repo_root).resolve()
    env_file_path = Path(args.env_file).resolve() if args.env_file else (repo_root / ".env")
    load_env_file(env_file_path)
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

"""CLI entrypoint setup for Forge."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import sys

from core.capability_model import build_request
from core.env_loader import load_env_file
from core.output_contracts import consume_last_contract, reset_last_contract
from core.run_history import append_run
from core.runtime import execute


REQUIRES_PAYLOAD = {
    "index": False,
    "doctor": False,
    "runs": False,
    "query": True,
    "explain": True,
    "review": True,
    "describe": False,
    "test": True,
}


FROM_RUN_CAPABILITIES = {"explain", "review", "describe", "test"}


def _nearest_forge_marker_root(start: Path) -> Path | None:
    current = start if start.is_dir() else start.parent
    for candidate in (current, *current.parents):
        marker = candidate / ".forge"
        if marker.is_dir():
            return candidate
    return None


def resolve_repo_root(raw_repo_root: str | None) -> Path:
    if raw_repo_root and raw_repo_root.strip():
        requested = Path(raw_repo_root).expanduser()
        candidate = requested.resolve() if requested.is_absolute() else (Path.cwd() / requested).resolve()
        if not candidate.exists():
            raise ValueError(f"--repo-root path does not exist: {candidate}")
    else:
        candidate = Path.cwd().resolve()
    resolved = _nearest_forge_marker_root(candidate)
    if resolved is not None:
        return resolved
    raise ValueError(
        "No initialized Forge repository found (nearest .forge/ marker missing). "
        f"Searched upward from: {candidate}. Run `forge init` in your repository root."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forge", description="Forge CLI")
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Optional start path; Forge auto-detects nearest ancestor with .forge/",
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
        "--view",
        choices=("compact", "standard", "full"),
        default="standard",
        help="Text output view mode (default: standard)",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Show full diagnostic details in text output (equivalent to --view full)",
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
    parser.add_argument(
        "--llm-output-language",
        help=(
            "Preferred LLM response language (e.g. de, en, de-DE, auto). "
            "Can also be set via FORGE_LLM_OUTPUT_LANGUAGE."
        ),
    )
    parser.add_argument(
        "--query-input-mode",
        choices=("planner", "exact"),
        default="planner",
        help="Query input processing mode: planner (LLM-assisted) or exact (no interpretation)",
    )
    subparsers = parser.add_subparsers(dest="capability", required=True)

    index_parser = subparsers.add_parser("index", help="Build or refresh repository index")
    index_parser.add_argument(
        "parts",
        nargs="*",
        help="Optional operation/profile prefix: simple|standard|detailed",
    )

    doctor_parser = subparsers.add_parser("doctor", help="Validate Forge config and runtime setup")
    doctor_parser.add_argument(
        "parts",
        nargs="*",
        help="Optional profile prefix: simple|standard|detailed",
    )
    doctor_parser.add_argument(
        "--check-llm-endpoint",
        action="store_true",
        help="Probe configured OpenAI-compatible endpoint (/models) with timeout",
    )

    config_parser = subparsers.add_parser("config", help="Configuration commands")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    config_validate_parser = config_subparsers.add_parser(
        "validate",
        help="Validate Forge config and runtime setup (alias for doctor)",
    )
    config_validate_parser.add_argument(
        "parts",
        nargs="*",
        help="Optional profile prefix: simple|standard|detailed",
    )
    config_validate_parser.add_argument(
        "--check-llm-endpoint",
        action="store_true",
        help="Probe configured OpenAI-compatible endpoint (/models) with timeout",
    )

    runs_parser = subparsers.add_parser("runs", help="Inspect or replay recorded capability runs")
    runs_parser.add_argument(
        "--keep-last",
        type=int,
        help="Retention override for prune: keep only the newest N runs",
    )
    runs_parser.add_argument(
        "--older-than-days",
        type=int,
        help="Retention override for prune: remove runs older than N days",
    )
    runs_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prune preview mode; show what would change without rewriting history",
    )
    runs_parser.add_argument(
        "parts",
        nargs="*",
        help=(
            "Examples: list | last | show <id> [compact|standard|full] | "
            "<id> show [view] | <id> rerun | prune"
        ),
    )

    query_parser = subparsers.add_parser("query", help="Run query capability")
    query_parser.add_argument(
        "parts",
        nargs="+",
        help="Question; optional profile prefix: simple|standard|detailed",
    )

    explain_parser = subparsers.add_parser("explain", help="Run explain capability")
    explain_parser.add_argument(
        "--from-run",
        type=int,
        help="Resolve explain target from a previous run id",
    )
    explain_parser.add_argument(
        "--confirm-transition",
        action="store_true",
        help="Explicitly confirm mode transition when using --from-run and transition policy requires it",
    )
    explain_parser.add_argument(
        "parts",
        nargs="*",
        help="Target; optional profile prefix: simple|standard|detailed (or use --from-run)",
    )

    review_parser = subparsers.add_parser("review", help="Run review capability")
    review_parser.add_argument(
        "--from-run",
        type=int,
        help="Resolve review target from a previous run id",
    )
    review_parser.add_argument(
        "--confirm-transition",
        action="store_true",
        help="Explicitly confirm mode transition when using --from-run and transition policy requires it",
    )
    review_parser.add_argument(
        "parts",
        nargs="*",
        help="Target; optional profile prefix: simple|standard|detailed (or use --from-run)",
    )

    describe_parser = subparsers.add_parser("describe", help="Run describe capability")
    describe_parser.add_argument(
        "--from-run",
        type=int,
        help="Resolve describe target from a previous run id",
    )
    describe_parser.add_argument(
        "--confirm-transition",
        action="store_true",
        help="Explicitly confirm mode transition when using --from-run and transition policy requires it",
    )
    describe_parser.add_argument(
        "parts",
        nargs="*",
        help="Optional target; optional profile prefix: simple|standard|detailed",
    )

    test_parser = subparsers.add_parser("test", help="Run test capability")
    test_parser.add_argument(
        "--from-run",
        type=int,
        help="Resolve test target from a previous run id",
    )
    test_parser.add_argument(
        "--confirm-transition",
        action="store_true",
        help="Explicitly confirm mode transition when using --from-run and transition policy requires it",
    )
    test_parser.add_argument(
        "parts",
        nargs="*",
        help="Target; optional profile prefix: simple|standard|detailed (or use --from-run)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        repo_root = resolve_repo_root(args.repo_root)
    except ValueError as exc:
        parser.error(str(exc))
        return 2
    args.repo_root = str(repo_root)
    env_file_path = Path(args.env_file).resolve() if args.env_file else (repo_root / ".env")
    load_env_file(env_file_path)
    parts = getattr(args, "parts", []) or []
    capability_name = args.capability
    if args.capability == "config":
        if getattr(args, "config_command", None) != "validate":
            parser.error("Unsupported config command. Use: forge config validate")
            return 2
        capability_name = "doctor"
    try:
        require_payload = REQUIRES_PAYLOAD[capability_name]
        if capability_name in FROM_RUN_CAPABILITIES and getattr(args, "from_run", None) is not None:
            require_payload = False
        request = build_request(
            capability_name=capability_name,
            parts=parts,
            require_payload=require_payload,
        )
    except ValueError as exc:
        parser.error(str(exc))
        return 2
    stdout_capture = io.StringIO()
    original_stdout = sys.stdout
    reset_last_contract()

    class _Tee:
        def write(self, data: str) -> int:
            stdout_capture.write(data)
            return original_stdout.write(data)

        def flush(self) -> None:
            stdout_capture.flush()
            original_stdout.flush()

    sys.stdout = _Tee()
    try:
        exit_code = execute(request=request, args=args)
    finally:
        sys.stdout = original_stdout

    if capability_name != "runs":
        text_output = stdout_capture.getvalue()
        contract_payload = consume_last_contract()
        if args.output_format == "json":
            try:
                parsed = json.loads(text_output)
                if isinstance(parsed, dict):
                    contract_payload = parsed
            except json.JSONDecodeError:
                pass
        if not isinstance(contract_payload, dict):
            contract_payload = {
                "capability": request.capability.value,
                "profile": request.profile.value,
                "summary": "Run completed without structured contract; fallback contract recorded.",
                "evidence": [],
                "uncertainty": [
                    "Capability did not emit a structured output contract in this code path."
                ],
                "next_step": "Re-run capability with --output-format json for full structured payload.",
                "sections": {"status": "fallback_contract"},
            }
        append_run(
            repo_root=repo_root,
            request={
                "capability": request.capability.value,
                "profile": request.profile.value,
                "payload": request.payload,
                "argv": argv or [],
            },
            execution={
                "exit_code": exit_code,
                "output_format": args.output_format,
            },
            output={
                "text": text_output,
                "contract": contract_payload,
            },
        )

    return exit_code

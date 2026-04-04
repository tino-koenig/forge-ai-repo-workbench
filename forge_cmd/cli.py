"""CLI entrypoint setup for Forge."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import sys
import time

from core.capability_model import Capability, build_request
from core.capability_model import CommandRequest, Profile
from core.env_loader import load_env_file
from core.init_foundation import (
    INIT_INDEX_ENRICHMENT_CHOICES,
    INIT_OUTPUT_LANGUAGE_CHOICES,
    INIT_REVIEW_STRICTNESS_CHOICES,
    INIT_SOURCE_SCOPE_CHOICES,
    INIT_TEMPLATE_CHOICES,
)
from core.output_contracts import consume_last_contract, reset_last_contract
from core.session_store import (
    ensure_active_session,
    get_active_session,
    record_activity,
)
from core.runtime_settings_resolver import resolve_runtime_settings
from core.runtime_settings_resolver import resolve_session_default_ttl_minutes
from core.run_history import append_run
from core.runtime import execute
from core.step_protocol import build_step_event, llm_step_events_from_usage


REQUIRES_PAYLOAD = {
    "init": False,
    "index": False,
    "doctor": False,
    "runs": False,
    "logs": False,
    "session": False,
    "set": False,
    "get": False,
    "query": True,
    "explain": True,
    "review": True,
    "describe": False,
    "test": True,
    "ask": True,
    "ask:repo": True,
    "ask:docs": True,
    "ask:latest": True,
    "explain:overview": True,
    "explain:symbols": True,
    "explain:dependencies": True,
    "explain:resources": True,
    "explain:uses": True,
    "explain:settings": True,
    "explain:defaults": True,
    "explain:llm": True,
    "explain:outputs": True,
}


FROM_RUN_CAPABILITIES = {"explain", "review", "describe", "test"}
PROFILE_VALUES = {Profile.SIMPLE.value, Profile.STANDARD.value, Profile.DETAILED.value}
_INIT_NON_MUTATING_STATUSES = {
    "invalid_target",
    "templates_listed",
    "dry_run",
    "canceled",
    "overwrite_blocked",
    "non_tty",
    "invalid_template",
}
_LOGS_CAPABILITY_CHOICES = tuple(sorted(capability.value for capability in Capability))


def _flag_present(argv_items: list[str], flag: str) -> bool:
    return any(item == flag or item.startswith(f"{flag}=") for item in argv_items)


def _should_persist_run_history(
    *,
    capability_name: str,
    exit_code: int,
    contract_payload: dict[str, object] | None,
) -> bool:
    if capability_name in {"runs", "logs"}:
        return False
    if capability_name != "init":
        return True
    if not isinstance(contract_payload, dict):
        return exit_code == 0
    sections = contract_payload.get("sections")
    if not isinstance(sections, dict):
        return exit_code == 0
    status = sections.get("status")
    if isinstance(status, str) and status in _INIT_NON_MUTATING_STATUSES:
        return False
    if exit_code != 0:
        return False
    return True


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

    init_parser = subparsers.add_parser("init", help="Initialize Forge configuration in a repository")
    init_parser.add_argument(
        "--template",
        choices=INIT_TEMPLATE_CHOICES,
        help="Init template id (default: balanced)",
    )
    init_parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Disable interactive prompts and use defaults/flags only",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Allow overwrite of existing init-managed files",
    )
    init_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview generated files without writing",
    )
    init_parser.add_argument(
        "--list-templates",
        action="store_true",
        help="List available templates and exit",
    )
    init_parser.add_argument(
        "--output-language",
        choices=INIT_OUTPUT_LANGUAGE_CHOICES,
        help="Override generated llm.prompt.output_language",
    )
    init_parser.add_argument(
        "--review-strictness",
        choices=INIT_REVIEW_STRICTNESS_CHOICES,
        help="Override generated review baseline strictness",
    )
    init_parser.add_argument(
        "--index-enrichment",
        choices=INIT_INDEX_ENRICHMENT_CHOICES,
        help="Override generated index enrichment setting",
    )
    init_parser.add_argument(
        "--source-scope",
        choices=INIT_SOURCE_SCOPE_CHOICES,
        help="Default retrieval source scope in generated config (repo_only|all)",
    )
    init_parser.add_argument(
        "--framework-allowlist",
        help="Optional comma-separated framework IDs/versions for generated source policy (e.g. typo3@12,symfony@7)",
    )
    init_parser.add_argument(
        "parts",
        nargs="*",
        help="Unused positional args (kept for command-model compatibility)",
    )

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

    logs_parser = subparsers.add_parser("logs", help="Inspect protocol events timeline")
    logs_parser.add_argument(
        "--run-id",
        dest="logs_run_id",
        type=int,
        help="Filter events by run id",
    )
    logs_parser.add_argument(
        "--capability",
        dest="logs_capability",
        choices=_LOGS_CAPABILITY_CHOICES,
        help="Filter by capability name",
    )
    logs_parser.add_argument(
        "--step-type",
        dest="logs_step_type",
        choices=("deterministic", "llm", "io", "policy"),
        help="Filter by protocol step type",
    )
    logs_parser.add_argument(
        "--status",
        dest="logs_status",
        choices=("started", "completed", "failed", "fallback"),
        help="Filter by step status",
    )
    logs_parser.add_argument(
        "--since",
        help="Filter events at/after ISO-8601 timestamp",
    )
    logs_parser.add_argument(
        "--until",
        help="Filter events at/before ISO-8601 timestamp",
    )
    logs_parser.add_argument(
        "--provider",
        dest="logs_provider",
        help="Filter by LLM provider metadata",
    )
    logs_parser.add_argument(
        "--model",
        dest="logs_model",
        help="Filter by LLM model metadata",
    )
    logs_parser.add_argument(
        "parts",
        nargs="*",
        help="Examples: tail [count] | run <run_id> | show <event_id> | stats",
    )

    query_parser = subparsers.add_parser("query", help="Run query capability")
    query_parser.add_argument(
        "--framework-profile",
        help="Optional framework profile id/alias from .forge/frameworks.toml",
    )
    query_parser.add_argument(
        "parts",
        nargs="+",
        help="Question; optional profile prefix: simple|standard|detailed",
    )

    ask_parser = subparsers.add_parser("ask", help="User-friendly ask entrypoint (maps to query)")
    ask_parser.add_argument(
        "--framework-profile",
        help="Optional framework profile id/alias from .forge/frameworks.toml",
    )
    ask_parser.add_argument(
        "--profile",
        dest="framework_profile",
        help="Alias for --framework-profile (ask preset profile selection)",
    )
    ask_parser.add_argument(
        "--guided",
        action="store_true",
        help="Reserved for later guided clarification mode (staged rollout).",
    )
    ask_parser.add_argument(
        "parts",
        nargs="+",
        help="Question; optional profile prefix: simple|standard|detailed",
    )

    ask_repo_parser = subparsers.add_parser("ask:repo", help="Ask with repository-focused source preset")
    ask_repo_parser.add_argument(
        "--framework-profile",
        help="Optional framework profile id/alias from .forge/frameworks.toml",
    )
    ask_repo_parser.add_argument(
        "--profile",
        dest="framework_profile",
        help="Alias for --framework-profile (ask preset profile selection)",
    )
    ask_repo_parser.add_argument(
        "--guided",
        action="store_true",
        help="Reserved for later guided clarification mode (staged rollout).",
    )
    ask_repo_parser.add_argument(
        "parts",
        nargs="+",
        help="Question; optional profile prefix: simple|standard|detailed",
    )

    ask_docs_parser = subparsers.add_parser("ask:docs", help="Ask with docs/framework-focused source preset")
    ask_docs_parser.add_argument(
        "--framework-profile",
        help="Optional framework profile id/alias from .forge/frameworks.toml",
    )
    ask_docs_parser.add_argument(
        "--profile",
        dest="framework_profile",
        help="Alias for --framework-profile (ask preset profile selection)",
    )
    ask_docs_parser.add_argument(
        "--guided",
        action="store_true",
        help="Reserved for later guided clarification mode (staged rollout).",
    )
    ask_docs_parser.add_argument(
        "parts",
        nargs="+",
        help="Question; optional profile prefix: simple|standard|detailed",
    )

    ask_latest_parser = subparsers.add_parser("ask:latest", help="Ask with latest/web-oriented source preset")
    ask_latest_parser.add_argument(
        "--framework-profile",
        help="Optional framework profile id/alias from .forge/frameworks.toml",
    )
    ask_latest_parser.add_argument(
        "--profile",
        dest="framework_profile",
        help="Alias for --framework-profile (ask preset profile selection)",
    )
    ask_latest_parser.add_argument(
        "--guided",
        action="store_true",
        help="Reserved for later guided clarification mode (staged rollout).",
    )
    ask_latest_parser.add_argument(
        "parts",
        nargs="+",
        help="Question; optional profile prefix: simple|standard|detailed",
    )

    def _add_explain_arguments(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--focus",
            choices=(
                "overview",
                "symbols",
                "dependencies",
                "resources",
                "uses",
                "settings",
                "defaults",
                "llm",
                "outputs",
            ),
            help="Explain focus facet (optional).",
        )
        p.add_argument(
            "--from-run",
            type=int,
            help="Resolve explain target from a previous run id",
        )
        p.add_argument(
            "--direction",
            choices=("out", "in"),
            default="out",
            help="Dependency direction for dependency-like facets.",
        )
        p.add_argument(
            "--source-scope",
            choices=("repo_only", "framework_only", "all"),
            default="repo_only",
            help="Source scope for dependency/resource facet analysis.",
        )
        p.add_argument(
            "--confirm-transition",
            action="store_true",
            help="Explicitly confirm mode transition when using --from-run and transition policy requires it",
        )
        p.add_argument(
            "parts",
            nargs="*",
            help="Target; optional profile prefix: simple|standard|detailed (or use --from-run)",
        )

    explain_parser = subparsers.add_parser("explain", help="Run explain capability")
    _add_explain_arguments(explain_parser)
    for alias in (
        "explain:overview",
        "explain:symbols",
        "explain:dependencies",
        "explain:resources",
        "explain:uses",
        "explain:settings",
        "explain:defaults",
        "explain:llm",
        "explain:outputs",
    ):
        alias_parser = subparsers.add_parser(alias, help=f"Run explain with facet alias '{alias.split(':', 1)[1]}'")
        _add_explain_arguments(alias_parser)

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

    session_parser = subparsers.add_parser("session", help="Manage named Forge runtime sessions")
    session_parser.add_argument(
        "--ttl-minutes",
        dest="session_ttl_minutes",
        type=int,
        default=60,
        help="TTL for newly created sessions (minutes, default: 60)",
    )
    session_parser.add_argument(
        "--revive",
        dest="session_revive",
        action="store_true",
        help="Revive expired session when using `session use`.",
    )
    session_parser.add_argument(
        "parts",
        nargs="*",
        help="Commands: new <name> | use <name> | list | show [name] | clear-context [name] | end [name]",
    )

    set_parser = subparsers.add_parser("set", help="Set runtime settings")
    set_parser.add_argument(
        "--scope",
        dest="set_scope",
        choices=("session", "repo", "user"),
        default="session",
        help="Persistence scope (default: session)",
    )
    set_parser.add_argument(
        "parts",
        nargs="*",
        help="Usage: set <key> <value> (aliases supported: output, llm, execution, access web|write)",
    )

    get_parser = subparsers.add_parser("get", help="Get runtime settings")
    get_parser.add_argument(
        "--scope",
        dest="get_scope",
        choices=("session", "repo", "user"),
        help="Read raw values from a specific scope",
    )
    get_parser.add_argument(
        "--resolved",
        dest="get_resolved",
        action="store_true",
        help="Resolve effective values across precedence even when --scope is set",
    )
    get_parser.add_argument(
        "--source",
        dest="get_source",
        action="store_true",
        help="Include per-key source information in resolved view",
    )
    get_parser.add_argument(
        "parts",
        nargs="*",
        help="Optional key/family selector (e.g. llm.mode, output, access web)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.capability == "init":
            raw = args.repo_root if args.repo_root else "."
            repo_root = Path(raw).expanduser().resolve()
        else:
            repo_root = resolve_repo_root(args.repo_root)
    except ValueError as exc:
        parser.error(str(exc))
        return 2
    args.repo_root = str(repo_root)
    env_file_path = Path(args.env_file).resolve() if args.env_file else (repo_root / ".env")
    load_env_file(env_file_path)
    argv_effective = argv or sys.argv[1:]
    parts = getattr(args, "parts", []) or []
    capability_name = args.capability
    ask_preset_map = {
        "ask": "auto",
        "ask:repo": "repo",
        "ask:docs": "docs",
        "ask:latest": "latest",
    }
    explain_focus_map = {
        "explain:overview": "overview",
        "explain:symbols": "symbols",
        "explain:dependencies": "dependencies",
        "explain:resources": "resources",
        "explain:uses": "uses",
        "explain:settings": "settings",
        "explain:defaults": "defaults",
        "explain:llm": "llm",
        "explain:outputs": "outputs",
    }
    requested_capability = capability_name
    if capability_name in ask_preset_map:
        capability_name = "ask"
        args.ask_preset = ask_preset_map[requested_capability]
        args.ask_mode = True
        args.ask_command = requested_capability
        args.ask_guided = bool(getattr(args, "guided", False))
        user_set_view = any(item == "--view" or item.startswith("--view=") for item in argv_effective)
        if not user_set_view and not getattr(args, "details", False):
            args.view = "compact"
    else:
        args.ask_preset = None
        args.ask_mode = False
        args.ask_command = None
        args.ask_guided = False
    if requested_capability in explain_focus_map:
        alias_focus = explain_focus_map[requested_capability]
        explicit_focus = getattr(args, "focus", None)
        if explicit_focus and explicit_focus != alias_focus:
            parser.error(
                f"Conflicting explain focus: alias '{requested_capability}' implies '{alias_focus}' "
                f"but --focus was '{explicit_focus}'."
            )
            return 2
        capability_name = "explain"
        args.explain_focus = alias_focus
        args.explain_focus_source = "alias"
        args.explain_command = requested_capability
    elif capability_name == "explain":
        explicit_focus = getattr(args, "focus", None)
        args.explain_focus = explicit_focus or "overview"
        args.explain_focus_source = "flag" if explicit_focus else "default"
        args.explain_command = "explain"
    else:
        args.explain_focus = None
        args.explain_focus_source = None
        args.explain_command = None

    runtime_consuming_capabilities = {
        "ask",
        "query",
        "explain",
        "review",
        "describe",
        "test",
    }
    args.active_session_name = None
    if capability_name in runtime_consuming_capabilities:
        session_ttl_minutes, _ttl_source, _ttl_warnings = resolve_session_default_ttl_minutes(repo_root, args=args)
        active_session, _auto_created, _session_warnings = ensure_active_session(
            repo_root,
            default_ttl_minutes=session_ttl_minutes,
        )
        args.active_session_name = active_session.name

    explicit_cli_values: dict[str, object] = {}
    output_format_explicit = _flag_present(argv_effective, "--output-format")
    view_explicit = _flag_present(argv_effective, "--view") or bool(getattr(args, "details", False))
    llm_mode_explicit = _flag_present(argv_effective, "--llm-mode")
    llm_model_explicit = _flag_present(argv_effective, "--llm-model")
    args.llm_mode_explicit = llm_mode_explicit
    args.llm_model_explicit = llm_model_explicit
    if output_format_explicit:
        explicit_cli_values["output.format"] = args.output_format
    if view_explicit:
        explicit_cli_values["output.view"] = "full" if getattr(args, "details", False) else args.view
    if llm_mode_explicit:
        explicit_cli_values["llm.mode"] = args.llm_mode
    if llm_model_explicit and getattr(args, "llm_model", None):
        explicit_cli_values["llm.model"] = args.llm_model

    runtime_resolution = resolve_runtime_settings(
        repo_root=repo_root,
        args=args,
        explicit_cli_values=explicit_cli_values,
    )
    args.runtime_settings_resolution = runtime_resolution
    args.runtime_settings_values = dict(runtime_resolution.values)
    args.runtime_settings_sources = dict(runtime_resolution.sources)

    if not output_format_explicit:
        runtime_output_format = runtime_resolution.values.get("output.format")
        if runtime_output_format in {"text", "json"}:
            args.output_format = str(runtime_output_format)
    if not view_explicit:
        runtime_view = runtime_resolution.values.get("output.view")
        if runtime_view in {"compact", "standard", "full"}:
            args.view = str(runtime_view)

    if args.capability == "config":
        if getattr(args, "config_command", None) != "validate":
            parser.error("Unsupported config command. Use: forge config validate")
            return 2
        capability_name = "doctor"
    preprocessing_started = time.perf_counter()
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

    profile_explicit = bool(parts and parts[0] in PROFILE_VALUES)
    if not profile_explicit:
        execution_profile = runtime_resolution.values.get("execution.profile")
        mapped_profile = {
            "fast": Profile.SIMPLE,
            "balanced": Profile.STANDARD,
            "intensive": Profile.DETAILED,
        }.get(str(execution_profile))
        if mapped_profile is not None and mapped_profile != request.profile:
            request = CommandRequest(
                capability=request.capability,
                profile=mapped_profile,
                payload=request.payload,
            )
    preprocessing_duration_ms = int((time.perf_counter() - preprocessing_started) * 1000)
    protocol_events: list[dict[str, object]] = [
        build_step_event(
            run_id=0,
            capability=request.capability.value,
            step_name="deterministic_preprocessing",
            step_type="deterministic",
            status="started",
            metadata={"argv_count": len(argv or [])},
        ),
        build_step_event(
            run_id=0,
            capability=request.capability.value,
            step_name="deterministic_preprocessing",
            step_type="deterministic",
            status="completed",
            duration_ms=preprocessing_duration_ms,
            metadata={"require_payload": require_payload},
        ),
        build_step_event(
            run_id=0,
            capability=request.capability.value,
            step_name="capability_execution",
            step_type="deterministic",
            status="started",
            metadata={"profile": request.profile.value},
        ),
    ]
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
    execution_started = time.perf_counter()
    try:
        exit_code = execute(request=request, args=args)
    finally:
        sys.stdout = original_stdout
    execution_duration_ms = int((time.perf_counter() - execution_started) * 1000)
    if exit_code == 0 and capability_name in runtime_consuming_capabilities:
        try:
            active, _warnings = get_active_session(repo_root)
            if active is not None:
                framework_hint = getattr(args, "framework_profile", None)
                record_activity(
                    repo_root,
                    capability=request.capability.value,
                    payload=request.payload,
                    framework_profile_hint=str(framework_hint) if isinstance(framework_hint, str) and framework_hint.strip() else None,
                )
        except Exception:
            # Activity retention must not break primary capability execution.
            pass
    protocol_events.append(
        build_step_event(
            run_id=0,
            capability=request.capability.value,
            step_name="capability_execution",
            step_type="deterministic",
            status="completed" if exit_code == 0 else "failed",
            duration_ms=execution_duration_ms,
            metadata={"exit_code": exit_code},
        )
    )

    if capability_name not in {"runs", "logs"}:
        assembly_started = time.perf_counter()
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
        assembly_duration_ms = int((time.perf_counter() - assembly_started) * 1000)
        protocol_events.extend(
            [
                build_step_event(
                    run_id=0,
                    capability=request.capability.value,
                    step_name="output_assembly",
                    step_type="io",
                    status="started",
                    metadata={"output_format": args.output_format},
                ),
                build_step_event(
                    run_id=0,
                    capability=request.capability.value,
                    step_name="output_assembly",
                    step_type="io",
                    status="completed",
                    duration_ms=assembly_duration_ms,
                    metadata={"has_contract": isinstance(contract_payload, dict)},
                ),
            ]
        )
        sections = contract_payload.get("sections", {}) if isinstance(contract_payload, dict) else {}
        if isinstance(sections, dict):
            protocol_events.extend(
                llm_step_events_from_usage(
                    run_id=0,
                    capability=request.capability.value,
                    step_name="summary_refinement",
                    usage=sections.get("llm_usage") if isinstance(sections.get("llm_usage"), dict) else None,
                )
            )
            planner = sections.get("query_planner")
            if isinstance(planner, dict):
                protocol_events.extend(
                    llm_step_events_from_usage(
                        run_id=0,
                        capability=request.capability.value,
                        step_name="query_planner",
                        usage=planner.get("usage") if isinstance(planner.get("usage"), dict) else None,
                    )
                )
            orchestration = sections.get("action_orchestration")
            if isinstance(orchestration, dict):
                protocol_events.extend(
                    llm_step_events_from_usage(
                        run_id=0,
                        capability=request.capability.value,
                        step_name="query_action_orchestrator",
                        usage=orchestration.get("usage") if isinstance(orchestration.get("usage"), dict) else None,
                    )
                )
        persist_run_history = _should_persist_run_history(
            capability_name=capability_name,
            exit_code=exit_code,
            contract_payload=contract_payload if isinstance(contract_payload, dict) else None,
        )
        if persist_run_history:
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
                    "protocol_events": protocol_events,
                },
                output={
                    "text": text_output,
                    "contract": contract_payload,
                },
            )

    return exit_code

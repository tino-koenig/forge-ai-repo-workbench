"""Configuration loading and precedence resolution for Forge."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import get_close_matches
from pathlib import Path
import os
from typing import Any

import tomli
from core.prompt_profiles import ALLOWED_PROMPT_PROFILES

_CONFIG_SCHEMA: dict[str, Any] = {
    "llm": {
        "provider": None,
        "openai_compatible": {
            "base_url": None,
            "model": None,
            "timeout_s": None,
            "api_key_env": None,
        },
        "request": {
            "context_budget_tokens": None,
            "max_output_tokens": None,
            "temperature": None,
        },
        "prompt": {
            "output_language": None,
            "profile": None,
            "system_template": None,
        },
        "query_planner": {
            "enabled": None,
            "mode": None,
            "max_terms": None,
            "max_code_variants": None,
            "max_latency_ms": None,
        },
        "query_orchestrator": {
            "enabled": None,
            "mode": None,
            "max_iterations": None,
            "max_files": None,
            "max_tokens": None,
            "max_wall_time_ms": None,
        },
        "observability": {
            "enabled": None,
            "level": None,
            "retention_count": None,
            "max_file_mb": None,
        },
        "cost_tracking": {
            "enabled": None,
            "warn_cost_per_request": None,
            "warn_tokens_per_request": None,
        },
        "pricing": {
            "input_per_1k": None,
            "output_per_1k": None,
            "currency": None,
        },
    },
    "index": {
        "enrichment": {
            "enabled": None,
            "summary_version": None,
            "max_summary_chars": None,
        },
    },
    "runs": {
        "retention": {
            "keep_last": None,
            "max_age_days": None,
            "max_file_mb": None,
        },
    },
    "graph": {
        "framework_refs": {"*": None},
    },
    "logs": {
        "protocol": {
            "max_file_size_bytes": None,
            "max_event_age_days": None,
            "max_events_count": None,
            "allow_full_prompt_until": None,
        },
    },
    "transitions": {
        "require_confirmation": None,
        "gates": {
            "review_to_test_min_severity": None,
            "test_to_fix_require_failure": None,
        },
    },
    "query": {
        "source_policy": {
            "source_scope_default": None,
            "framework_allowlist": {"*": None},
        },
    },
    "session": {
        "default_ttl_minutes": None,
    },
}

DEFAULT_QUERY_PLANNER_ENABLED = True
DEFAULT_QUERY_PLANNER_MAX_TERMS = 12
DEFAULT_QUERY_PLANNER_MAX_CODE_VARIANTS = 8
DEFAULT_QUERY_PLANNER_MAX_LATENCY_MS = 2500
DEFAULT_QUERY_ORCHESTRATOR_ENABLED = True
DEFAULT_QUERY_ORCHESTRATOR_MAX_ITERATIONS = 2
DEFAULT_QUERY_ORCHESTRATOR_MAX_FILES = 8
DEFAULT_QUERY_ORCHESTRATOR_MAX_TOKENS = 1200
DEFAULT_QUERY_ORCHESTRATOR_MAX_WALL_TIME_MS = 2500
DEFAULT_LOGS_PROTOCOL_MAX_FILE_SIZE_BYTES = 5_000_000
DEFAULT_LOGS_PROTOCOL_MAX_EVENT_AGE_DAYS = 30
DEFAULT_LOGS_PROTOCOL_MAX_EVENTS_COUNT = 50_000


@dataclass(frozen=True)
class ResolvedLLMConfig:
    mode: str
    provider: str | None
    base_url: str | None
    model: str | None
    timeout_s: float
    api_key_env: str
    api_key: str | None
    context_budget_tokens: int
    max_output_tokens: int
    temperature: float
    output_language: str
    prompt_profile: str
    system_template_path: Path
    query_planner_enabled: bool
    query_planner_mode: str
    query_planner_max_terms: int
    query_planner_max_code_variants: int
    query_planner_max_latency_ms: int
    query_orchestrator_enabled: bool
    query_orchestrator_mode: str
    query_orchestrator_max_iterations: int
    query_orchestrator_max_files: int
    query_orchestrator_max_tokens: int
    query_orchestrator_max_wall_time_ms: int
    observability_enabled: bool
    observability_level: str
    observability_retention_count: int
    observability_max_file_mb: int
    cost_tracking_enabled: bool
    cost_warn_cost_per_request: float | None
    cost_warn_tokens_per_request: int | None
    pricing_input_per_1k: float | None
    pricing_output_per_1k: float | None
    pricing_currency: str
    source: dict[str, str]
    validation_error: str | None = None


@dataclass(frozen=True)
class ResolvedProtocolLogConfig:
    max_file_size_bytes: int
    max_event_age_days: int
    max_events_count: int
    allow_full_prompt_until: datetime | None
    source: dict[str, str]
    validation_errors: list[str]


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return tomli.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomli.TOMLDecodeError) as exc:
        return {"_error": f"invalid TOML config: {exc}"}


def _nested_get(data: dict[str, Any], path: str) -> Any:
    cursor: Any = data
    for part in path.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            return None
        cursor = cursor[part]
    return cursor


def _first_non_none(pairs: list[tuple[str, Any]]) -> tuple[Any, str]:
    for source, value in pairs:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value, source
    return None, "default"


def _float_or_default(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_or_default(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool_or_default(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _default_system_template() -> Path:
    return Path(__file__).resolve().parents[1] / "prompts" / "system" / "default_read_only.txt"


def _normalize_output_language(value: Any) -> str:
    if value is None:
        return "auto"
    candidate = str(value).strip()
    if not candidate:
        return "auto"
    lowered = candidate.lower()
    if lowered in {"auto", "same"}:
        return "auto"
    if len(candidate) > 32:
        return "invalid"
    if not all(ch.isalnum() or ch == "-" for ch in candidate):
        return "invalid"
    parts = [part for part in candidate.split("-") if part]
    if not parts:
        return "invalid"
    if not (2 <= len(parts[0]) <= 3 and parts[0].isalpha()):
        return "invalid"
    for part in parts[1:]:
        if not (1 <= len(part) <= 8 and part.isalnum()):
            return "invalid"
    return "-".join(parts)


def _parse_iso_utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _collect_schema_paths(schema: dict[str, Any], prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for key, child in schema.items():
        if key == "*":
            continue
        current = f"{prefix}.{key}" if prefix else key
        paths.add(current)
        if isinstance(child, dict):
            paths.update(_collect_schema_paths(child, current))
    return paths


def _find_unknown_config_keys(
    payload: dict[str, Any],
    *,
    schema: dict[str, Any],
    source_label: str,
) -> list[str]:
    known_paths = sorted(_collect_schema_paths(schema))
    findings: list[str] = []

    def walk(node: dict[str, Any], node_schema: dict[str, Any], prefix: str = "") -> None:
        for key, value in node.items():
            if not isinstance(key, str):
                continue
            current = f"{prefix}.{key}" if prefix else key
            if key in node_schema:
                next_schema = node_schema.get(key)
                if isinstance(next_schema, dict) and isinstance(value, dict):
                    walk(value, next_schema, current)
                continue
            if "*" in node_schema:
                wildcard_schema = node_schema.get("*")
                if isinstance(wildcard_schema, dict) and isinstance(value, dict):
                    walk(value, wildcard_schema, current)
                continue
            suggestion = get_close_matches(current, known_paths, n=1, cutoff=0.72)
            if suggestion:
                findings.append(f"{source_label}: unknown key '{current}' (did you mean '{suggestion[0]}'?)")
            else:
                findings.append(f"{source_label}: unknown key '{current}'")

    walk(payload, schema)
    return findings


def resolve_llm_config(args, repo_root: Path) -> ResolvedLLMConfig:
    config_path = repo_root / ".forge" / "config.toml"
    local_config_path = repo_root / ".forge" / "config.local.toml"
    payload = _load_toml(config_path)
    local_payload = _load_toml(local_config_path)
    runtime_values = getattr(args, "runtime_settings_values", {})
    runtime_sources = getattr(args, "runtime_settings_sources", {})
    if not isinstance(runtime_values, dict):
        runtime_values = {}
    if not isinstance(runtime_sources, dict):
        runtime_sources = {}

    def _runtime_candidate(key: str) -> tuple[str, Any]:
        if key not in runtime_values:
            return "runtime", None
        source_tag = str(runtime_sources.get(key) or "session")
        return f"runtime_{source_tag}", runtime_values.get(key)

    mode_cli = getattr(args, "llm_mode", None) if bool(getattr(args, "llm_mode_explicit", False)) else None
    mode_runtime_source, mode_runtime_value = _runtime_candidate("llm.mode")
    mode_raw, mode_source = _first_non_none(
        [
            ("cli", mode_cli),
            (mode_runtime_source, mode_runtime_value),
            ("default", "auto"),
        ]
    )
    resolved_mode = str(mode_raw or "auto")

    if "_error" in payload:
        return ResolvedLLMConfig(
            mode=resolved_mode,
            provider=None,
            base_url=None,
            model=None,
            timeout_s=30.0,
            api_key_env="FORGE_LLM_API_KEY",
            api_key=None,
            context_budget_tokens=12000,
            max_output_tokens=700,
            temperature=0.2,
            output_language="auto",
            prompt_profile="strict_read_only",
            system_template_path=_default_system_template(),
            query_planner_enabled=DEFAULT_QUERY_PLANNER_ENABLED,
            query_planner_mode="optional",
            query_planner_max_terms=DEFAULT_QUERY_PLANNER_MAX_TERMS,
            query_planner_max_code_variants=DEFAULT_QUERY_PLANNER_MAX_CODE_VARIANTS,
            query_planner_max_latency_ms=DEFAULT_QUERY_PLANNER_MAX_LATENCY_MS,
            query_orchestrator_enabled=DEFAULT_QUERY_ORCHESTRATOR_ENABLED,
            query_orchestrator_mode="optional",
            query_orchestrator_max_iterations=DEFAULT_QUERY_ORCHESTRATOR_MAX_ITERATIONS,
            query_orchestrator_max_files=DEFAULT_QUERY_ORCHESTRATOR_MAX_FILES,
            query_orchestrator_max_tokens=DEFAULT_QUERY_ORCHESTRATOR_MAX_TOKENS,
            query_orchestrator_max_wall_time_ms=DEFAULT_QUERY_ORCHESTRATOR_MAX_WALL_TIME_MS,
            observability_enabled=False,
            observability_level="minimal",
            observability_retention_count=1000,
            observability_max_file_mb=20,
            cost_tracking_enabled=True,
            cost_warn_cost_per_request=None,
            cost_warn_tokens_per_request=None,
            pricing_input_per_1k=None,
            pricing_output_per_1k=None,
            pricing_currency="USD",
            source={"mode": mode_source, "config": "error"},
            validation_error=str(payload["_error"]),
        )
    if "_error" in local_payload:
        return ResolvedLLMConfig(
            mode=resolved_mode,
            provider=None,
            base_url=None,
            model=None,
            timeout_s=30.0,
            api_key_env="FORGE_LLM_API_KEY",
            api_key=None,
            context_budget_tokens=12000,
            max_output_tokens=700,
            temperature=0.2,
            output_language="auto",
            prompt_profile="strict_read_only",
            system_template_path=_default_system_template(),
            query_planner_enabled=DEFAULT_QUERY_PLANNER_ENABLED,
            query_planner_mode="optional",
            query_planner_max_terms=DEFAULT_QUERY_PLANNER_MAX_TERMS,
            query_planner_max_code_variants=DEFAULT_QUERY_PLANNER_MAX_CODE_VARIANTS,
            query_planner_max_latency_ms=DEFAULT_QUERY_PLANNER_MAX_LATENCY_MS,
            query_orchestrator_enabled=DEFAULT_QUERY_ORCHESTRATOR_ENABLED,
            query_orchestrator_mode="optional",
            query_orchestrator_max_iterations=DEFAULT_QUERY_ORCHESTRATOR_MAX_ITERATIONS,
            query_orchestrator_max_files=DEFAULT_QUERY_ORCHESTRATOR_MAX_FILES,
            query_orchestrator_max_tokens=DEFAULT_QUERY_ORCHESTRATOR_MAX_TOKENS,
            query_orchestrator_max_wall_time_ms=DEFAULT_QUERY_ORCHESTRATOR_MAX_WALL_TIME_MS,
            observability_enabled=False,
            observability_level="minimal",
            observability_retention_count=1000,
            observability_max_file_mb=20,
            cost_tracking_enabled=True,
            cost_warn_cost_per_request=None,
            cost_warn_tokens_per_request=None,
            pricing_input_per_1k=None,
            pricing_output_per_1k=None,
            pricing_currency="USD",
            source={"mode": mode_source, "config.local": "error"},
            validation_error=str(local_payload["_error"]),
        )

    source: dict[str, str] = {}
    source["mode"] = mode_source
    provider, source["provider"] = _first_non_none(
        [
            ("cli", getattr(args, "llm_provider", None)),
            ("env", os.environ.get("FORGE_LLM_PROVIDER")),
            ("toml_local", _nested_get(local_payload, "llm.provider")),
            ("toml", _nested_get(payload, "llm.provider")),
        ]
    )
    base_url, source["base_url"] = _first_non_none(
        [
            ("cli", getattr(args, "llm_base_url", None)),
            ("env", os.environ.get("FORGE_LLM_BASE_URL")),
            ("toml_local", _nested_get(local_payload, "llm.openai_compatible.base_url")),
            ("toml", _nested_get(payload, "llm.openai_compatible.base_url")),
        ]
    )
    model, source["model"] = _first_non_none(
        [
            ("cli", getattr(args, "llm_model", None)),
            _runtime_candidate("llm.model"),
            ("env", os.environ.get("FORGE_LLM_MODEL")),
            ("toml_local", _nested_get(local_payload, "llm.openai_compatible.model")),
            ("toml", _nested_get(payload, "llm.openai_compatible.model")),
        ]
    )

    timeout_raw, source["timeout_s"] = _first_non_none(
        [
            ("cli", getattr(args, "llm_timeout_s", None)),
            ("env", os.environ.get("FORGE_LLM_TIMEOUT_S")),
            ("toml_local", _nested_get(local_payload, "llm.openai_compatible.timeout_s")),
            ("toml", _nested_get(payload, "llm.openai_compatible.timeout_s")),
        ]
    )
    timeout_s = _float_or_default(timeout_raw, 30.0)

    api_key_env_name, source["api_key_env"] = _first_non_none(
        [
            ("env", os.environ.get("FORGE_LLM_API_KEY_ENV")),
            ("toml_local", _nested_get(local_payload, "llm.openai_compatible.api_key_env")),
            ("toml", _nested_get(payload, "llm.openai_compatible.api_key_env")),
            ("default", "FORGE_LLM_API_KEY"),
        ]
    )
    api_key_env = str(api_key_env_name)
    api_key = os.environ.get(api_key_env)

    context_budget_raw, source["context_budget_tokens"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.request.context_budget_tokens")),
            ("toml", _nested_get(payload, "llm.request.context_budget_tokens")),
        ]
    )
    max_output_raw, source["max_output_tokens"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.request.max_output_tokens")),
            ("toml", _nested_get(payload, "llm.request.max_output_tokens")),
        ]
    )
    temperature_raw, source["temperature"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.request.temperature")),
            ("toml", _nested_get(payload, "llm.request.temperature")),
        ]
    )
    context_budget_tokens = _int_or_default(context_budget_raw, 12000)
    max_output_tokens = _int_or_default(max_output_raw, 700)
    temperature = _float_or_default(temperature_raw, 0.2)
    output_language_raw, source["output_language"] = _first_non_none(
        [
            ("cli", getattr(args, "llm_output_language", None)),
            ("env", os.environ.get("FORGE_LLM_OUTPUT_LANGUAGE")),
            ("toml_local", _nested_get(local_payload, "llm.prompt.output_language")),
            ("toml", _nested_get(payload, "llm.prompt.output_language")),
            ("default", "auto"),
        ]
    )
    output_language = _normalize_output_language(output_language_raw)

    prompt_profile_raw, source["prompt_profile"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.prompt.profile")),
            ("toml", _nested_get(payload, "llm.prompt.profile")),
            ("default", "strict_read_only"),
        ]
    )
    prompt_profile = str(prompt_profile_raw)

    system_template_raw, source["system_template"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.prompt.system_template")),
            ("toml", _nested_get(payload, "llm.prompt.system_template")),
        ]
    )
    if isinstance(system_template_raw, str) and system_template_raw.strip():
        system_template = Path(system_template_raw.strip())
        system_template_path = (
            system_template if system_template.is_absolute() else (repo_root / system_template).resolve()
        )
    else:
        system_template_path = _default_system_template()

    planner_enabled_raw, source["query_planner_enabled"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.query_planner.enabled")),
            ("toml", _nested_get(payload, "llm.query_planner.enabled")),
            ("default", DEFAULT_QUERY_PLANNER_ENABLED),
        ]
    )
    planner_mode_raw, source["query_planner_mode"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.query_planner.mode")),
            ("toml", _nested_get(payload, "llm.query_planner.mode")),
            ("default", "optional"),
        ]
    )
    planner_max_terms_raw, source["query_planner_max_terms"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.query_planner.max_terms")),
            ("toml", _nested_get(payload, "llm.query_planner.max_terms")),
            ("default", DEFAULT_QUERY_PLANNER_MAX_TERMS),
        ]
    )
    planner_max_code_variants_raw, source["query_planner_max_code_variants"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.query_planner.max_code_variants")),
            ("toml", _nested_get(payload, "llm.query_planner.max_code_variants")),
            ("default", DEFAULT_QUERY_PLANNER_MAX_CODE_VARIANTS),
        ]
    )
    planner_max_latency_ms_raw, source["query_planner_max_latency_ms"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.query_planner.max_latency_ms")),
            ("toml", _nested_get(payload, "llm.query_planner.max_latency_ms")),
            ("default", DEFAULT_QUERY_PLANNER_MAX_LATENCY_MS),
        ]
    )
    query_planner_enabled = _bool_or_default(planner_enabled_raw, DEFAULT_QUERY_PLANNER_ENABLED)
    query_planner_mode = str(planner_mode_raw).strip().lower()
    query_planner_max_terms = _int_or_default(planner_max_terms_raw, DEFAULT_QUERY_PLANNER_MAX_TERMS)
    query_planner_max_code_variants = _int_or_default(
        planner_max_code_variants_raw, DEFAULT_QUERY_PLANNER_MAX_CODE_VARIANTS
    )
    query_planner_max_latency_ms = _int_or_default(planner_max_latency_ms_raw, DEFAULT_QUERY_PLANNER_MAX_LATENCY_MS)
    orchestrator_enabled_raw, source["query_orchestrator_enabled"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.query_orchestrator.enabled")),
            ("toml", _nested_get(payload, "llm.query_orchestrator.enabled")),
            ("default", DEFAULT_QUERY_ORCHESTRATOR_ENABLED),
        ]
    )
    orchestrator_mode_raw, source["query_orchestrator_mode"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.query_orchestrator.mode")),
            ("toml", _nested_get(payload, "llm.query_orchestrator.mode")),
            ("default", "optional"),
        ]
    )
    orchestrator_max_iterations_raw, source["query_orchestrator_max_iterations"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.query_orchestrator.max_iterations")),
            ("toml", _nested_get(payload, "llm.query_orchestrator.max_iterations")),
            ("default", DEFAULT_QUERY_ORCHESTRATOR_MAX_ITERATIONS),
        ]
    )
    orchestrator_max_files_raw, source["query_orchestrator_max_files"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.query_orchestrator.max_files")),
            ("toml", _nested_get(payload, "llm.query_orchestrator.max_files")),
            ("default", DEFAULT_QUERY_ORCHESTRATOR_MAX_FILES),
        ]
    )
    orchestrator_max_tokens_raw, source["query_orchestrator_max_tokens"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.query_orchestrator.max_tokens")),
            ("toml", _nested_get(payload, "llm.query_orchestrator.max_tokens")),
            ("default", DEFAULT_QUERY_ORCHESTRATOR_MAX_TOKENS),
        ]
    )
    orchestrator_max_wall_time_ms_raw, source["query_orchestrator_max_wall_time_ms"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.query_orchestrator.max_wall_time_ms")),
            ("toml", _nested_get(payload, "llm.query_orchestrator.max_wall_time_ms")),
            ("default", DEFAULT_QUERY_ORCHESTRATOR_MAX_WALL_TIME_MS),
        ]
    )
    query_orchestrator_enabled = _bool_or_default(orchestrator_enabled_raw, DEFAULT_QUERY_ORCHESTRATOR_ENABLED)
    query_orchestrator_mode = str(orchestrator_mode_raw).strip().lower()
    query_orchestrator_max_iterations = _int_or_default(
        orchestrator_max_iterations_raw, DEFAULT_QUERY_ORCHESTRATOR_MAX_ITERATIONS
    )
    query_orchestrator_max_files = _int_or_default(orchestrator_max_files_raw, DEFAULT_QUERY_ORCHESTRATOR_MAX_FILES)
    query_orchestrator_max_tokens = _int_or_default(
        orchestrator_max_tokens_raw, DEFAULT_QUERY_ORCHESTRATOR_MAX_TOKENS
    )
    query_orchestrator_max_wall_time_ms = _int_or_default(
        orchestrator_max_wall_time_ms_raw, DEFAULT_QUERY_ORCHESTRATOR_MAX_WALL_TIME_MS
    )

    observability_enabled_raw, source["observability_enabled"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.observability.enabled")),
            ("toml", _nested_get(payload, "llm.observability.enabled")),
            ("default", False),
        ]
    )
    observability_level_raw, source["observability_level"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.observability.level")),
            ("toml", _nested_get(payload, "llm.observability.level")),
            ("default", "minimal"),
        ]
    )
    observability_retention_count_raw, source["observability_retention_count"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.observability.retention_count")),
            ("toml", _nested_get(payload, "llm.observability.retention_count")),
            ("default", 1000),
        ]
    )
    observability_max_file_mb_raw, source["observability_max_file_mb"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.observability.max_file_mb")),
            ("toml", _nested_get(payload, "llm.observability.max_file_mb")),
            ("default", 20),
        ]
    )
    observability_enabled = _bool_or_default(observability_enabled_raw, False)
    observability_level = str(observability_level_raw).strip().lower()
    observability_retention_count = _int_or_default(observability_retention_count_raw, 1000)
    observability_max_file_mb = _int_or_default(observability_max_file_mb_raw, 20)

    cost_tracking_enabled_raw, source["cost_tracking_enabled"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.cost_tracking.enabled")),
            ("toml", _nested_get(payload, "llm.cost_tracking.enabled")),
            ("default", True),
        ]
    )
    cost_warn_cost_raw, source["cost_warn_cost_per_request"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.cost_tracking.warn_cost_per_request")),
            ("toml", _nested_get(payload, "llm.cost_tracking.warn_cost_per_request")),
        ]
    )
    cost_warn_tokens_raw, source["cost_warn_tokens_per_request"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.cost_tracking.warn_tokens_per_request")),
            ("toml", _nested_get(payload, "llm.cost_tracking.warn_tokens_per_request")),
        ]
    )
    pricing_input_raw, source["pricing_input_per_1k"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.pricing.input_per_1k")),
            ("toml", _nested_get(payload, "llm.pricing.input_per_1k")),
        ]
    )
    pricing_output_raw, source["pricing_output_per_1k"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.pricing.output_per_1k")),
            ("toml", _nested_get(payload, "llm.pricing.output_per_1k")),
        ]
    )
    pricing_currency_raw, source["pricing_currency"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.pricing.currency")),
            ("toml", _nested_get(payload, "llm.pricing.currency")),
            ("default", "USD"),
        ]
    )
    cost_tracking_enabled = _bool_or_default(cost_tracking_enabled_raw, True)
    cost_warn_cost_per_request = (
        _float_or_default(cost_warn_cost_raw, -1.0) if cost_warn_cost_raw is not None else None
    )
    if isinstance(cost_warn_cost_per_request, float) and cost_warn_cost_per_request < 0:
        cost_warn_cost_per_request = None
    cost_warn_tokens_per_request = (
        _int_or_default(cost_warn_tokens_raw, -1) if cost_warn_tokens_raw is not None else None
    )
    if isinstance(cost_warn_tokens_per_request, int) and cost_warn_tokens_per_request < 0:
        cost_warn_tokens_per_request = None
    pricing_input_per_1k = _float_or_default(pricing_input_raw, -1.0) if pricing_input_raw is not None else None
    if isinstance(pricing_input_per_1k, float) and pricing_input_per_1k < 0:
        pricing_input_per_1k = None
    pricing_output_per_1k = _float_or_default(pricing_output_raw, -1.0) if pricing_output_raw is not None else None
    if isinstance(pricing_output_per_1k, float) and pricing_output_per_1k < 0:
        pricing_output_per_1k = None
    pricing_currency = str(pricing_currency_raw).strip().upper() if pricing_currency_raw is not None else "USD"
    if not pricing_currency:
        pricing_currency = "USD"

    validation_errors: list[str] = []
    validation_errors.extend(_find_unknown_config_keys(payload, schema=_CONFIG_SCHEMA, source_label="config.toml"))
    validation_errors.extend(
        _find_unknown_config_keys(local_payload, schema=_CONFIG_SCHEMA, source_label="config.local.toml")
    )
    protocol_config = resolve_protocol_log_config(repo_root)
    validation_errors.extend(protocol_config.validation_errors)
    if provider is not None and provider not in {"openai_compatible", "mock"}:
        validation_errors.append(f"unknown provider '{provider}'")
    if provider == "openai_compatible":
        if not isinstance(base_url, str) or not base_url.strip():
            validation_errors.append("openai_compatible.base_url is required when provider=openai_compatible")
        if not isinstance(model, str) or not model.strip():
            validation_errors.append("openai_compatible.model is required when provider=openai_compatible")
        if not isinstance(api_key_env, str) or not api_key_env.strip():
            validation_errors.append("openai_compatible.api_key_env must be a non-empty env var name")
    if timeout_s <= 0:
        validation_errors.append("timeout_s must be > 0")
    if context_budget_tokens <= 0:
        validation_errors.append("context_budget_tokens must be > 0")
    if max_output_tokens <= 0:
        validation_errors.append("max_output_tokens must be > 0")
    if temperature < 0 or temperature > 2:
        validation_errors.append("temperature must be within [0, 2]")
    if output_language == "invalid":
        validation_errors.append(
            "llm.prompt.output_language must be auto or BCP-47-like (e.g. de, en, de-DE)"
        )
    if prompt_profile not in ALLOWED_PROMPT_PROFILES:
        validation_errors.append(f"unknown prompt profile '{prompt_profile}'")
    source_scope_default = _nested_get(local_payload, "query.source_policy.source_scope_default")
    if source_scope_default is None:
        source_scope_default = _nested_get(payload, "query.source_policy.source_scope_default")
    if source_scope_default is not None and str(source_scope_default).strip().lower() not in {"repo_only", "all"}:
        validation_errors.append("query.source_policy.source_scope_default must be one of: repo_only, all")
    if query_planner_mode not in {"off", "optional", "preferred"}:
        validation_errors.append(
            f"unknown query planner mode '{query_planner_mode}' (expected off|optional|preferred)"
        )
    if query_planner_max_terms <= 0 or query_planner_max_terms > 64:
        validation_errors.append("query_planner.max_terms must be within [1, 64]")
    if query_planner_max_code_variants < 0 or query_planner_max_code_variants > 64:
        validation_errors.append("query_planner.max_code_variants must be within [0, 64]")
    if query_planner_max_latency_ms < 200 or query_planner_max_latency_ms > 120000:
        validation_errors.append("query_planner.max_latency_ms must be within [200, 120000]")
    if query_orchestrator_mode not in {"off", "optional", "preferred"}:
        validation_errors.append(
            f"unknown query orchestrator mode '{query_orchestrator_mode}' (expected off|optional|preferred)"
        )
    if query_orchestrator_max_iterations < 1 or query_orchestrator_max_iterations > 8:
        validation_errors.append("query_orchestrator.max_iterations must be within [1, 8]")
    if query_orchestrator_max_files < 1 or query_orchestrator_max_files > 200:
        validation_errors.append("query_orchestrator.max_files must be within [1, 200]")
    if query_orchestrator_max_tokens < 100 or query_orchestrator_max_tokens > 8000:
        validation_errors.append("query_orchestrator.max_tokens must be within [100, 8000]")
    if query_orchestrator_max_wall_time_ms < 200 or query_orchestrator_max_wall_time_ms > 120000:
        validation_errors.append("query_orchestrator.max_wall_time_ms must be within [200, 120000]")
    if observability_level not in {"minimal", "standard", "debug"}:
        validation_errors.append("observability.level must be one of: minimal, standard, debug")
    if observability_retention_count < 100 or observability_retention_count > 100000:
        validation_errors.append("observability.retention_count must be within [100, 100000]")
    if observability_max_file_mb < 1 or observability_max_file_mb > 1024:
        validation_errors.append("observability.max_file_mb must be within [1, 1024]")
    if cost_warn_cost_per_request is not None and cost_warn_cost_per_request < 0:
        validation_errors.append("cost_tracking.warn_cost_per_request must be >= 0")
    if cost_warn_tokens_per_request is not None and cost_warn_tokens_per_request < 0:
        validation_errors.append("cost_tracking.warn_tokens_per_request must be >= 0")
    if pricing_input_per_1k is not None and pricing_input_per_1k < 0:
        validation_errors.append("pricing.input_per_1k must be >= 0")
    if pricing_output_per_1k is not None and pricing_output_per_1k < 0:
        validation_errors.append("pricing.output_per_1k must be >= 0")
    if len(pricing_currency) > 12 or not pricing_currency.replace("_", "").isalnum():
        validation_errors.append("pricing.currency must be an uppercase currency-like code")
    if not system_template_path.exists():
        validation_errors.append(f"missing system template: {system_template_path}")
    elif not system_template_path.is_file():
        validation_errors.append(f"system template is not a file: {system_template_path}")
    elif not os.access(system_template_path, os.R_OK):
        validation_errors.append(f"system template not readable: {system_template_path}")

    validation_error = "; ".join(validation_errors) if validation_errors else None

    return ResolvedLLMConfig(
        mode=resolved_mode,
        provider=str(provider) if isinstance(provider, str) else None,
        base_url=str(base_url) if isinstance(base_url, str) else None,
        model=str(model) if isinstance(model, str) else None,
        timeout_s=timeout_s,
        api_key_env=api_key_env,
        api_key=api_key,
        context_budget_tokens=context_budget_tokens,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        output_language=output_language,
        prompt_profile=prompt_profile,
        system_template_path=system_template_path,
        query_planner_enabled=query_planner_enabled,
        query_planner_mode=query_planner_mode,
        query_planner_max_terms=query_planner_max_terms,
        query_planner_max_code_variants=query_planner_max_code_variants,
        query_planner_max_latency_ms=query_planner_max_latency_ms,
        query_orchestrator_enabled=query_orchestrator_enabled,
        query_orchestrator_mode=query_orchestrator_mode,
        query_orchestrator_max_iterations=query_orchestrator_max_iterations,
        query_orchestrator_max_files=query_orchestrator_max_files,
        query_orchestrator_max_tokens=query_orchestrator_max_tokens,
        query_orchestrator_max_wall_time_ms=query_orchestrator_max_wall_time_ms,
        observability_enabled=observability_enabled,
        observability_level=observability_level,
        observability_retention_count=observability_retention_count,
        observability_max_file_mb=observability_max_file_mb,
        cost_tracking_enabled=cost_tracking_enabled,
        cost_warn_cost_per_request=cost_warn_cost_per_request,
        cost_warn_tokens_per_request=cost_warn_tokens_per_request,
        pricing_input_per_1k=pricing_input_per_1k,
        pricing_output_per_1k=pricing_output_per_1k,
        pricing_currency=pricing_currency,
        source=source,
        validation_error=validation_error,
    )


def resolve_protocol_log_config(repo_root: Path) -> ResolvedProtocolLogConfig:
    config_path = repo_root / ".forge" / "config.toml"
    local_config_path = repo_root / ".forge" / "config.local.toml"
    payload = _load_toml(config_path)
    local_payload = _load_toml(local_config_path)
    source: dict[str, str] = {}

    max_file_size_raw, source["max_file_size_bytes"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "logs.protocol.max_file_size_bytes")),
            ("toml", _nested_get(payload, "logs.protocol.max_file_size_bytes")),
            ("default", DEFAULT_LOGS_PROTOCOL_MAX_FILE_SIZE_BYTES),
        ]
    )
    max_event_age_raw, source["max_event_age_days"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "logs.protocol.max_event_age_days")),
            ("toml", _nested_get(payload, "logs.protocol.max_event_age_days")),
            ("default", DEFAULT_LOGS_PROTOCOL_MAX_EVENT_AGE_DAYS),
        ]
    )
    max_events_count_raw, source["max_events_count"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "logs.protocol.max_events_count")),
            ("toml", _nested_get(payload, "logs.protocol.max_events_count")),
            ("default", DEFAULT_LOGS_PROTOCOL_MAX_EVENTS_COUNT),
        ]
    )
    allow_prompt_raw, source["allow_full_prompt_until"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "logs.protocol.allow_full_prompt_until")),
            ("toml", _nested_get(payload, "logs.protocol.allow_full_prompt_until")),
        ]
    )

    validation_errors: list[str] = []
    max_file_size_bytes = _int_or_default(max_file_size_raw, DEFAULT_LOGS_PROTOCOL_MAX_FILE_SIZE_BYTES)
    max_event_age_days = _int_or_default(max_event_age_raw, DEFAULT_LOGS_PROTOCOL_MAX_EVENT_AGE_DAYS)
    max_events_count = _int_or_default(max_events_count_raw, DEFAULT_LOGS_PROTOCOL_MAX_EVENTS_COUNT)
    if max_file_size_raw is not None and not isinstance(max_file_size_raw, int):
        try:
            int(str(max_file_size_raw).strip())
        except (TypeError, ValueError):
            validation_errors.append("logs.protocol.max_file_size_bytes must be an integer")
    if max_event_age_raw is not None and not isinstance(max_event_age_raw, int):
        try:
            int(str(max_event_age_raw).strip())
        except (TypeError, ValueError):
            validation_errors.append("logs.protocol.max_event_age_days must be an integer")
    if max_events_count_raw is not None and not isinstance(max_events_count_raw, int):
        try:
            int(str(max_events_count_raw).strip())
        except (TypeError, ValueError):
            validation_errors.append("logs.protocol.max_events_count must be an integer")
    if max_file_size_bytes < 1024 or max_file_size_bytes > 500_000_000:
        validation_errors.append("logs.protocol.max_file_size_bytes must be within [1024, 500000000]")
    if max_event_age_days < 1 or max_event_age_days > 36500:
        validation_errors.append("logs.protocol.max_event_age_days must be within [1, 36500]")
    if max_events_count < 100 or max_events_count > 5_000_000:
        validation_errors.append("logs.protocol.max_events_count must be within [100, 5000000]")
    if max_file_size_bytes < 1024:
        max_file_size_bytes = 1024
    if max_file_size_bytes > 500_000_000:
        max_file_size_bytes = 500_000_000
    if max_event_age_days < 1:
        max_event_age_days = 1
    if max_event_age_days > 36500:
        max_event_age_days = 36500
    if max_events_count < 100:
        max_events_count = 100
    if max_events_count > 5_000_000:
        max_events_count = 5_000_000
    allow_full_prompt_until = _parse_iso_utc(allow_prompt_raw)
    if allow_prompt_raw is not None and allow_full_prompt_until is None:
        validation_errors.append("logs.protocol.allow_full_prompt_until must be an ISO-8601 timestamp")

    return ResolvedProtocolLogConfig(
        max_file_size_bytes=max_file_size_bytes,
        max_event_age_days=max_event_age_days,
        max_events_count=max_events_count,
        allow_full_prompt_until=allow_full_prompt_until,
        source=source,
        validation_errors=validation_errors,
    )

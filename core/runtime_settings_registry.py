"""Canonical runtime settings registry for resolver-driven overrides."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeSettingSpec:
    key: str
    value_type: str  # enum|bool|string|int|float
    allowed_values: tuple[str, ...] | None
    default: Any
    scope_support: frozenset[str]
    description: str


RUNTIME_SETTINGS_REGISTRY: dict[str, RuntimeSettingSpec] = {
    "output.format": RuntimeSettingSpec(
        key="output.format",
        value_type="enum",
        allowed_values=("text", "json"),
        default="text",
        scope_support=frozenset({"session", "repo", "user"}),
        description="Output transport format.",
    ),
    "output.view": RuntimeSettingSpec(
        key="output.view",
        value_type="enum",
        allowed_values=("compact", "standard", "full"),
        default="standard",
        scope_support=frozenset({"session", "repo", "user"}),
        description="Text output detail view.",
    ),
    "llm.mode": RuntimeSettingSpec(
        key="llm.mode",
        value_type="enum",
        allowed_values=("off", "auto", "force"),
        default="auto",
        scope_support=frozenset({"session", "repo", "user"}),
        description="LLM invocation mode.",
    ),
    "llm.model": RuntimeSettingSpec(
        key="llm.model",
        value_type="string",
        allowed_values=None,
        default=None,
        scope_support=frozenset({"session", "repo", "user"}),
        description="LLM model override.",
    ),
    "execution.profile": RuntimeSettingSpec(
        key="execution.profile",
        value_type="enum",
        allowed_values=("fast", "balanced", "intensive"),
        default="balanced",
        scope_support=frozenset({"session", "repo", "user"}),
        description="Execution effort profile.",
    ),
    "access.web": RuntimeSettingSpec(
        key="access.web",
        value_type="bool",
        allowed_values=None,
        default=False,
        scope_support=frozenset({"session", "repo", "user"}),
        description="Allow web-oriented retrieval paths.",
    ),
    "access.write": RuntimeSettingSpec(
        key="access.write",
        value_type="bool",
        allowed_values=None,
        default=False,
        scope_support=frozenset({"session", "repo", "user"}),
        description="Allow write-capable workflows where contracts permit it.",
    ),
    "session.default_ttl_minutes": RuntimeSettingSpec(
        key="session.default_ttl_minutes",
        value_type="int",
        allowed_values=None,
        default=60,
        scope_support=frozenset({"session", "repo", "user"}),
        description="Default TTL for auto-created sessions in minutes.",
    ),
}


def list_runtime_specs() -> list[RuntimeSettingSpec]:
    return [RUNTIME_SETTINGS_REGISTRY[key] for key in sorted(RUNTIME_SETTINGS_REGISTRY)]


def runtime_spec_for(key: str) -> RuntimeSettingSpec | None:
    return RUNTIME_SETTINGS_REGISTRY.get(key)


def _normalize_key(raw_key: str) -> str:
    return " ".join(raw_key.strip().lower().replace("_", ".").split())


def _parse_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


def _parse_value(spec: RuntimeSettingSpec, value: object) -> object | None:
    if spec.value_type == "bool":
        return _parse_bool(value)
    if spec.value_type == "string":
        if value is None:
            return None
        rendered = str(value).strip()
        return rendered if rendered else None
    rendered = str(value).strip().lower() if value is not None else ""
    if spec.value_type == "enum":
        if spec.allowed_values and rendered in spec.allowed_values:
            return rendered
        return None
    if spec.value_type == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if spec.value_type == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def expand_runtime_alias(
    raw_key: str,
    raw_value: object,
) -> tuple[dict[str, object], list[dict[str, object]], list[str]]:
    """Normalize one raw assignment into canonical runtime keys."""
    warnings: list[str] = []
    trace: list[dict[str, object]] = []
    key_norm = _normalize_key(raw_key)

    alias_map = {
        "llm": "llm.mode",
        "llm mode": "llm.mode",
        "llm.model": "llm.model",
        "llm model": "llm.model",
        "execution": "execution.profile",
        "execution profile": "execution.profile",
        "access web": "access.web",
        "access.write": "access.write",
        "access write": "access.write",
        "session default ttl": "session.default_ttl_minutes",
        "session.default.ttl.minutes": "session.default_ttl_minutes",
        "session.default_ttl_minutes": "session.default_ttl_minutes",
    }

    if key_norm == "output":
        preset = str(raw_value).strip().lower()
        if preset == "human":
            expanded = {"output.format": "text", "output.view": "standard"}
        elif preset == "json":
            expanded = {"output.format": "json"}
        elif preset == "exhaustive":
            expanded = {"output.format": "text", "output.view": "full"}
        else:
            warnings.append(
                "invalid alias value for 'output'; expected one of: human, json, exhaustive"
            )
            return {}, trace, warnings
        for canonical, value in expanded.items():
            trace.append(
                {
                    "raw_key": raw_key,
                    "canonical_key": canonical,
                    "raw_value": raw_value,
                    "normalized_value": value,
                    "via_alias": "output",
                }
            )
        return expanded, trace, warnings

    canonical_key = alias_map.get(key_norm, key_norm)
    spec = runtime_spec_for(canonical_key)
    if spec is None:
        warnings.append(f"unknown runtime setting key '{raw_key}'")
        return {}, trace, warnings

    parsed_value = _parse_value(spec, raw_value)
    if parsed_value is None and spec.default is not None:
        allowed = ", ".join(spec.allowed_values or ())
        suffix = f"; allowed values: {allowed}" if allowed else ""
        warnings.append(f"invalid value for '{canonical_key}': {raw_value!r}{suffix}")
        return {}, trace, warnings

    if parsed_value is None and spec.default is None:
        # nullable string values are allowed to pass through as empty meaning unset.
        parsed_value = None

    trace.append(
        {
            "raw_key": raw_key,
            "canonical_key": canonical_key,
            "raw_value": raw_value,
            "normalized_value": parsed_value,
            "via_alias": canonical_key != key_norm,
        }
    )
    return {canonical_key: parsed_value}, trace, warnings

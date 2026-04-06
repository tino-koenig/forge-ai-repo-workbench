"""Runtime Settings Foundation (04): typed resolver with diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from core.runtime_settings_foundation_registry import (
    RUNTIME_SETTINGS_FOUNDATION_REGISTRY,
    SettingSpec,
)

SOURCE_PRIORITY: tuple[str, ...] = ("cli", "local", "repo")
DEFAULT_SOURCE = "default"

CODE_UNKNOWN_KEY = "unknown_key"
CODE_INVALID_TYPE = "invalid_type"
CODE_OUT_OF_BOUNDS = "out_of_bounds"
CODE_UNKNOWN_ENUM_VALUE = "unknown_enum_value"
CODE_DEFAULT_FALLBACK_BLOCKED = "default_fallback_blocked"
CODE_INVALID_DEFAULT = "invalid_default"


@dataclass(frozen=True)
class SettingDiagnostic:
    key: str
    raw_value: object
    source: str
    reason: str
    fallback_source: str | None
    code: str


@dataclass(frozen=True)
class ResolvedSetting:
    key: str
    value: int | float | bool | str | None
    source: str
    diagnostics: tuple[SettingDiagnostic, ...]


def _normalize_string(value: str, spec: SettingSpec) -> str:
    normalized = value
    for rule in spec.normalize:
        if rule == "strip":
            normalized = normalized.strip()
        elif rule == "lowercase":
            normalized = normalized.lower()
    return normalized


def _next_fallback_source(
    key: str,
    sources: Mapping[str, Mapping[str, object]],
    from_source: str,
) -> str:
    from_index = SOURCE_PRIORITY.index(from_source)
    for candidate in SOURCE_PRIORITY[from_index + 1 :]:
        candidate_values = sources.get(candidate, {})
        if key in candidate_values:
            return candidate
    return DEFAULT_SOURCE


def _parse_bool(value: object) -> tuple[bool | None, str | None, str | None]:
    if isinstance(value, bool):
        return value, None, None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "1", "yes", "on"):
            return True, None, None
        if normalized in ("false", "0", "no", "off"):
            return False, None, None
    return None, CODE_INVALID_TYPE, "Expected bool-like value."


def _parse_int(value: object) -> tuple[int | None, str | None, str | None]:
    if isinstance(value, bool):
        return None, CODE_INVALID_TYPE, "Expected int but got bool."
    if isinstance(value, int):
        return value, None, None
    if isinstance(value, str):
        candidate = value.strip()
        try:
            return int(candidate), None, None
        except ValueError:
            return None, CODE_INVALID_TYPE, "Expected integer value."
    return None, CODE_INVALID_TYPE, "Expected integer value."


def _parse_float(value: object) -> tuple[float | None, str | None, str | None]:
    if isinstance(value, bool):
        return None, CODE_INVALID_TYPE, "Expected float but got bool."
    if isinstance(value, (int, float)):
        return float(value), None, None
    if isinstance(value, str):
        candidate = value.strip()
        try:
            return float(candidate), None, None
        except ValueError:
            return None, CODE_INVALID_TYPE, "Expected floating-point value."
    return None, CODE_INVALID_TYPE, "Expected floating-point value."


def _validate_bounds(value: int | float, spec: SettingSpec) -> tuple[bool, str | None, str | None]:
    if spec.min is not None and value < spec.min:
        return False, CODE_OUT_OF_BOUNDS, f"Value below minimum ({spec.min})."
    if spec.max is not None and value > spec.max:
        return False, CODE_OUT_OF_BOUNDS, f"Value above maximum ({spec.max})."
    return True, None, None


def _coerce_value(raw_value: object, spec: SettingSpec) -> tuple[int | float | bool | str | None, str | None, str | None]:
    if spec.kind == "bool":
        return _parse_bool(raw_value)

    if spec.kind == "int":
        parsed_int, code, reason = _parse_int(raw_value)
        if code is not None:
            return None, code, reason
        if parsed_int is None:
            return None, CODE_INVALID_TYPE, "Expected integer value."
        in_bounds, bounds_code, bounds_reason = _validate_bounds(parsed_int, spec)
        if not in_bounds:
            return None, bounds_code, bounds_reason
        return parsed_int, None, None

    if spec.kind == "float":
        parsed_float, code, reason = _parse_float(raw_value)
        if code is not None:
            return None, code, reason
        if parsed_float is None:
            return None, CODE_INVALID_TYPE, "Expected floating-point value."
        in_bounds, bounds_code, bounds_reason = _validate_bounds(parsed_float, spec)
        if not in_bounds:
            return None, bounds_code, bounds_reason
        return parsed_float, None, None

    if spec.kind == "enum":
        if not isinstance(raw_value, str):
            return None, CODE_INVALID_TYPE, "Expected string enum value."
        normalized = _normalize_string(raw_value, spec)
        allowed = spec.allowed_values or tuple()
        if normalized not in allowed:
            return None, CODE_UNKNOWN_ENUM_VALUE, "Value not in allowed enum set."
        return normalized, None, None

    if spec.kind == "str":
        if not isinstance(raw_value, str):
            return None, CODE_INVALID_TYPE, "Expected string value."
        return _normalize_string(raw_value, spec), None, None

    return None, CODE_INVALID_TYPE, f"Unsupported setting kind '{spec.kind}'."


def resolve_setting(
    key: str,
    sources: Mapping[str, Mapping[str, object]],
    registry: Mapping[str, SettingSpec] | None = None,
) -> ResolvedSetting:
    active_registry = registry or RUNTIME_SETTINGS_FOUNDATION_REGISTRY
    spec = active_registry.get(key)

    if spec is None:
        unknown_key_diagnostics: list[SettingDiagnostic] = []
        for source in SOURCE_PRIORITY:
            values = sources.get(source, {})
            if key in values:
                unknown_key_diagnostics.append(
                    SettingDiagnostic(
                        key=key,
                        raw_value=values[key],
                        source=source,
                        reason="Key is not defined in runtime settings registry.",
                        fallback_source=DEFAULT_SOURCE,
                        code=CODE_UNKNOWN_KEY,
                    )
                )
        if not unknown_key_diagnostics:
            unknown_key_diagnostics.append(
                SettingDiagnostic(
                    key=key,
                    raw_value=None,
                    source=DEFAULT_SOURCE,
                    reason="Key is not defined in runtime settings registry.",
                    fallback_source=DEFAULT_SOURCE,
                    code=CODE_UNKNOWN_KEY,
                )
            )
        return ResolvedSetting(
            key=key,
            value=None,
            source=DEFAULT_SOURCE,
            diagnostics=tuple(unknown_key_diagnostics),
        )

    diagnostics: list[SettingDiagnostic] = []
    for source in SOURCE_PRIORITY:
        source_values = sources.get(source, {})
        if key not in source_values:
            continue

        raw_value = source_values[key]
        parsed, code, reason = _coerce_value(raw_value, spec)
        if code is None:
            return ResolvedSetting(
                key=key,
                value=parsed,
                source=source,
                diagnostics=tuple(diagnostics),
            )

        diagnostics.append(
            SettingDiagnostic(
                key=key,
                raw_value=raw_value,
                source=source,
                reason=reason or "Invalid value.",
                fallback_source=_next_fallback_source(key, sources, source),
                code=code,
            )
        )

    if spec.allow_default_fallback:
        parsed_default, default_code, default_reason = _coerce_value(spec.default, spec)
        if default_code is None:
            return ResolvedSetting(
                key=key,
                value=parsed_default,
                source=DEFAULT_SOURCE,
                diagnostics=tuple(diagnostics),
            )
        diagnostics.append(
            SettingDiagnostic(
                key=key,
                raw_value=spec.default,
                source=DEFAULT_SOURCE,
                reason=default_reason or "Configured default is invalid for setting spec.",
                fallback_source=None,
                code=CODE_INVALID_DEFAULT,
            )
        )
        return ResolvedSetting(
            key=key,
            value=None,
            source=DEFAULT_SOURCE,
            diagnostics=tuple(diagnostics),
        )

    diagnostics.append(
        SettingDiagnostic(
            key=key,
            raw_value=None,
            source=DEFAULT_SOURCE,
            reason="Default fallback is disabled for this setting.",
            fallback_source=None,
            code=CODE_DEFAULT_FALLBACK_BLOCKED,
        )
    )
    return ResolvedSetting(
        key=key,
        value=None,
        source=DEFAULT_SOURCE,
        diagnostics=tuple(diagnostics),
    )


def resolve_settings(
    keys: Sequence[str],
    sources: Mapping[str, Mapping[str, object]],
    registry: Mapping[str, SettingSpec] | None = None,
) -> dict[str, ResolvedSetting]:
    active_registry = registry or RUNTIME_SETTINGS_FOUNDATION_REGISTRY

    resolved: dict[str, ResolvedSetting] = {}
    seen: set[str] = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        resolved[key] = resolve_setting(key, sources, active_registry)
    return resolved


__all__ = [
    "CODE_DEFAULT_FALLBACK_BLOCKED",
    "CODE_INVALID_TYPE",
    "CODE_INVALID_DEFAULT",
    "CODE_OUT_OF_BOUNDS",
    "CODE_UNKNOWN_ENUM_VALUE",
    "CODE_UNKNOWN_KEY",
    "DEFAULT_SOURCE",
    "ResolvedSetting",
    "SettingDiagnostic",
    "SettingSpec",
    "SOURCE_PRIORITY",
    "resolve_setting",
    "resolve_settings",
]

"""Runtime settings resolver with deterministic precedence and source tracing."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

import tomli

from core.runtime_settings_registry import (
    RUNTIME_SETTINGS_REGISTRY,
    expand_runtime_alias,
    list_runtime_specs,
    runtime_spec_for,
)


@dataclass(frozen=True)
class RuntimeSettingsResolution:
    values: dict[str, object]
    sources: dict[str, str]
    normalization: list[dict[str, object]]
    warnings: list[str]
    scope_paths: dict[str, str]
    raw_scopes: dict[str, dict[str, object]]

    def as_dict(self) -> dict[str, object]:
        return {
            "values": self.values,
            "sources": self.sources,
            "normalization": self.normalization,
            "warnings": self.warnings,
            "scope_paths": self.scope_paths,
            "raw_scopes": self.raw_scopes,
        }


def default_user_runtime_path() -> Path:
    env_override = os.environ.get("FORGE_USER_RUNTIME_TOML")
    if env_override:
        return Path(env_override).expanduser().resolve()
    xdg_base = os.environ.get("XDG_CONFIG_HOME")
    if xdg_base:
        return (Path(xdg_base).expanduser() / "forge" / "runtime.toml").resolve()
    return (Path.home() / ".config" / "forge" / "runtime.toml").resolve()


def _flatten_mapping(mapping: dict[str, Any], prefix: str = "") -> dict[str, object]:
    flat: dict[str, object] = {}
    for raw_key, value in mapping.items():
        if not isinstance(raw_key, str):
            continue
        key = f"{prefix}.{raw_key}" if prefix else raw_key
        if isinstance(value, dict):
            flat.update(_flatten_mapping(value, key))
        else:
            flat[key] = value
    return flat


def _load_toml(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        parsed = tomli.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomli.TOMLDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _read_scope_assignments(scope: str, payload: dict[str, object] | None) -> tuple[dict[str, object], list[dict[str, object]], list[str]]:
    if payload is None:
        return {}, [], []
    flat = _flatten_mapping(payload)
    out: dict[str, object] = {}
    normalization: list[dict[str, object]] = []
    warnings: list[str] = []
    for raw_key, raw_value in flat.items():
        expanded, trace, local_warnings = expand_runtime_alias(raw_key, raw_value)
        for item in local_warnings:
            warnings.append(f"{scope}: {item}")
        for item in trace:
            item_with_scope = dict(item)
            item_with_scope["scope"] = scope
            normalization.append(item_with_scope)
        for canonical_key, parsed_value in expanded.items():
            spec = runtime_spec_for(canonical_key)
            if spec is None:
                continue
            if scope not in spec.scope_support:
                warnings.append(f"{scope}: key '{canonical_key}' is not supported in this scope")
                continue
            out[canonical_key] = parsed_value
    return out, normalization, warnings


def _session_scope_payload(args) -> dict[str, object] | None:
    explicit = getattr(args, "runtime_session_values", None)
    if isinstance(explicit, dict):
        return explicit
    raw = os.environ.get("FORGE_RUNTIME_SESSION_JSON")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _baseline_from_repo_config(repo_root: Path) -> dict[str, object]:
    """Subset bridge from existing repo config into runtime canonical keys."""
    config_path = repo_root / ".forge" / "config.toml"
    local_path = repo_root / ".forge" / "config.local.toml"
    payload = _load_toml(config_path) or {}
    local_payload = _load_toml(local_path) or {}
    flat = _flatten_mapping(payload)
    local_flat = _flatten_mapping(local_payload)

    def pick(path: str) -> object:
        if path in local_flat:
            return local_flat[path]
        return flat.get(path)

    baseline: dict[str, object] = {}
    llm_model = pick("llm.openai_compatible.model")
    if isinstance(llm_model, str) and llm_model.strip():
        baseline["llm.model"] = llm_model.strip()
    return baseline


def resolve_runtime_settings(
    *,
    repo_root: Path,
    args,
    explicit_cli_values: dict[str, object] | None = None,
) -> RuntimeSettingsResolution:
    explicit_cli_values = explicit_cli_values or {}
    warnings: list[str] = []
    normalization: list[dict[str, object]] = []

    repo_runtime_path = repo_root / ".forge" / "runtime.toml"
    user_runtime_path = default_user_runtime_path()
    scope_paths = {
        "session": "env:FORGE_RUNTIME_SESSION_JSON",
        "repo": str(repo_runtime_path),
        "user": str(user_runtime_path),
        "toml": str(repo_root / ".forge" / "config.toml"),
    }

    session_payload = _session_scope_payload(args)
    repo_payload = _load_toml(repo_runtime_path)
    user_payload = _load_toml(user_runtime_path)
    baseline_toml = _baseline_from_repo_config(repo_root)

    session_values, session_norm, session_warnings = _read_scope_assignments("session", session_payload)
    repo_values, repo_norm, repo_warnings = _read_scope_assignments("repo", repo_payload)
    user_values, user_norm, user_warnings = _read_scope_assignments("user", user_payload)
    normalization.extend(session_norm)
    normalization.extend(repo_norm)
    normalization.extend(user_norm)
    warnings.extend(session_warnings)
    warnings.extend(repo_warnings)
    warnings.extend(user_warnings)

    values: dict[str, object] = {}
    sources: dict[str, str] = {}
    for spec in list_runtime_specs():
        key = spec.key
        if key in explicit_cli_values:
            values[key] = explicit_cli_values[key]
            sources[key] = "cli"
            continue
        if key in session_values:
            values[key] = session_values[key]
            sources[key] = "session"
            continue
        if key in repo_values:
            values[key] = repo_values[key]
            sources[key] = "repo"
            continue
        if key in user_values:
            values[key] = user_values[key]
            sources[key] = "user"
            continue
        if key in baseline_toml:
            values[key] = baseline_toml[key]
            sources[key] = "toml"
            continue
        values[key] = spec.default
        sources[key] = "default"

    # Guard unknown explicit CLI overrides.
    for key in explicit_cli_values:
        if key in RUNTIME_SETTINGS_REGISTRY:
            continue
        warnings.append(f"cli: unknown runtime key '{key}'")

    return RuntimeSettingsResolution(
        values=values,
        sources=sources,
        normalization=normalization,
        warnings=warnings,
        scope_paths=scope_paths,
        raw_scopes={
            "session": session_values,
            "repo": repo_values,
            "user": user_values,
            "toml": baseline_toml,
        },
    )


def write_runtime_scope_stub(scope: str, values: dict[str, object], repo_root: Path) -> tuple[bool, str]:
    """Writer stub for future set/get command surface (feature 061)."""
    if scope == "repo":
        target = repo_root / ".forge" / "runtime.toml"
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# generated by runtime settings writer stub"]
        for key in sorted(values):
            val = values[key]
            rendered = json.dumps(val)
            lines.append(f'"{key}" = {rendered}')
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True, str(target)
    if scope == "user":
        target = default_user_runtime_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# generated by runtime settings writer stub"]
        for key in sorted(values):
            val = values[key]
            rendered = json.dumps(val)
            lines.append(f'"{key}" = {rendered}')
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True, str(target)
    if scope == "session":
        return False, "session scope writer is intentionally in-memory/stub-only in feature 062"
    return False, f"unsupported runtime scope: {scope}"

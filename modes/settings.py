from __future__ import annotations

from difflib import get_close_matches
from pathlib import Path

from core.capability_model import CommandRequest, EffectClass
from core.effects import ExecutionSession
from core.output_contracts import build_contract, emit_contract_json
from core.output_views import is_full, resolve_view
from core.runtime_settings_registry import expand_runtime_alias, list_runtime_specs, runtime_spec_for
from core.runtime_settings_resolver import load_runtime_scope, resolve_runtime_settings, save_runtime_scope


ALL_KEYS = [spec.key for spec in list_runtime_specs()]
FAMILY_MAP = {
    "output": ["output.format", "output.view"],
    "llm": ["llm.mode", "llm.model"],
    "execution": ["execution.profile"],
    "access": ["access.web", "access.write"],
    "session": ["session.default_ttl_minutes"],
}
KEY_ALIASES = {
    "llm mode": "llm.mode",
    "llm.model": "llm.model",
    "llm model": "llm.model",
    "execution profile": "execution.profile",
    "access web": "access.web",
    "access.write": "access.write",
    "access write": "access.write",
    "output format": "output.format",
    "output view": "output.view",
    "session default ttl": "session.default_ttl_minutes",
    "session.default.ttl.minutes": "session.default_ttl_minutes",
    "session.default_ttl_minutes": "session.default_ttl_minutes",
}


def _normalize_key(raw: str) -> str:
    return " ".join(raw.strip().lower().replace("_", ".").split())


def _contract(
    request: CommandRequest,
    *,
    summary: str,
    next_step: str,
    sections: dict[str, object],
    uncertainty: list[str] | None = None,
) -> dict[str, object]:
    return build_contract(
        capability=request.capability.value,
        profile=request.profile.value,
        summary=summary,
        evidence=[],
        uncertainty=uncertainty or [],
        next_step=next_step,
        sections=sections,
    )


def _render_text(args, contract: dict[str, object], title: str) -> int:
    view = resolve_view(args)
    print(title)
    print(f"Profile: {contract.get('profile')}")
    print("\n--- Summary ---")
    print(contract.get("summary", ""))
    sections = contract.get("sections", {})
    if is_full(view):
        print("\n--- Settings ---")
        for key in sorted(sections.keys()):
            print(f"{key}: {sections[key]}")
    print("\n--- Next Step ---")
    print(contract.get("next_step", ""))
    if contract.get("uncertainty"):
        print("\n--- Uncertainty ---")
        for note in contract.get("uncertainty", []):
            print(f"- {note}")
    return 0


def _error(args, request: CommandRequest, message: str) -> int:
    contract = _contract(
        request,
        summary=f"Runtime settings command failed: {message}",
        next_step="Run: forge get --source",
        sections={"status": "error"},
        uncertainty=[message],
    )
    if args.output_format == "json":
        emit_contract_json(contract)
        return 1
    _render_text(args, contract, "=== FORGE SETTINGS ===")
    return 1


def _suggest_key(raw_key: str) -> str | None:
    options = sorted(set(ALL_KEYS + list(FAMILY_MAP.keys()) + list(KEY_ALIASES.keys())))
    matches = get_close_matches(raw_key, options, n=1, cutoff=0.6)
    return matches[0] if matches else None


def _select_keys(raw_key: str | None) -> tuple[list[str] | None, str | None]:
    if raw_key is None or not raw_key.strip():
        return list(ALL_KEYS), None
    key_norm = _normalize_key(raw_key)
    if key_norm in FAMILY_MAP:
        return list(FAMILY_MAP[key_norm]), None
    alias_target = KEY_ALIASES.get(key_norm)
    if alias_target:
        return [alias_target], None
    direct = key_norm.replace(" ", ".")
    if direct in ALL_KEYS:
        return [direct], None
    suggestion = _suggest_key(key_norm)
    if suggestion:
        return None, f"unknown runtime key '{raw_key}' (did you mean '{suggestion}'?)"
    return None, f"unknown runtime key '{raw_key}'"


def _parse_set_parts(parts: list[str]) -> tuple[str, str]:
    if len(parts) < 2:
        raise ValueError("set requires: forge set <key> <value> [--scope ...]")
    first = parts[0].strip().lower()
    if first == "access" and len(parts) >= 3 and parts[1].strip().lower() in {"web", "write"}:
        return f"access {parts[1].strip().lower()}", " ".join(parts[2:]).strip()
    if first == "llm" and len(parts) >= 3 and parts[1].strip().lower() == "model":
        return "llm model", " ".join(parts[2:]).strip()
    if first == "llm" and len(parts) >= 3 and parts[1].strip().lower() == "mode":
        return "llm mode", " ".join(parts[2:]).strip()
    if first == "execution" and len(parts) >= 3 and parts[1].strip().lower() == "profile":
        return "execution profile", " ".join(parts[2:]).strip()
    return parts[0], " ".join(parts[1:]).strip()


def _apply_scope_support(scope: str, values: dict[str, object]) -> str | None:
    for key in values:
        spec = runtime_spec_for(key)
        if spec is None:
            return f"unknown runtime key '{key}'"
        if scope not in spec.scope_support:
            return f"key '{key}' is not supported in scope '{scope}'"
        if key == "session.default_ttl_minutes":
            value = values.get(key)
            if not isinstance(value, int) or value < 1 or value > 24 * 60:
                return "session.default_ttl_minutes must be within [1, 1440]"
    return None


def run_set(request: CommandRequest, args, session: ExecutionSession) -> int:
    repo_root = Path(args.repo_root).resolve()
    scope = str(getattr(args, "set_scope", "session") or "session")
    parts = getattr(args, "parts", []) or []
    session.record_effect(EffectClass.READ_ONLY, f"read runtime settings ({scope} scope)")

    try:
        raw_key, raw_value = _parse_set_parts(parts)
    except ValueError as exc:
        return _error(args, request, str(exc))

    expanded, trace, warnings = expand_runtime_alias(raw_key, raw_value)
    if not expanded:
        err = warnings[0] if warnings else f"could not normalize runtime setting '{raw_key}'"
        if err.startswith("unknown runtime setting key"):
            suggestion = _suggest_key(_normalize_key(raw_key))
            if suggestion:
                err = f"{err} (did you mean '{suggestion}'?)"
        return _error(args, request, err)
    support_error = _apply_scope_support(scope, expanded)
    if support_error:
        return _error(args, request, support_error)

    current_values, _norm, scope_warnings, _origin = load_runtime_scope(scope, repo_root)
    merged = dict(current_values)
    for key, value in expanded.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value

    ok, target = save_runtime_scope(scope, merged, repo_root)
    if not ok:
        return _error(args, request, target)
    session.record_effect(EffectClass.FORGE_WRITE, f"write runtime settings ({scope} -> {target})")

    resolution = resolve_runtime_settings(repo_root=repo_root, args=args, explicit_cli_values={})
    touched = sorted(expanded.keys())
    resolved_values = {key: resolution.values.get(key) for key in touched}
    resolved_sources = {key: resolution.sources.get(key) for key in touched}
    uncertainty = [*warnings, *scope_warnings]
    contract = _contract(
        request,
        summary=f"Updated {len(touched)} runtime setting(s) in scope '{scope}'.",
        next_step="Run: forge get --source",
        sections={
            "settings": {
                "scope": scope,
                "target": target,
                "updated": expanded,
                "aliases_applied": trace,
                "resolved_values": resolved_values,
                "resolved_sources": resolved_sources,
            }
        },
        uncertainty=uncertainty,
    )
    if args.output_format == "json":
        emit_contract_json(contract)
        return 0
    return _render_text(args, contract, "=== FORGE SET ===")


def run_get(request: CommandRequest, args, session: ExecutionSession) -> int:
    repo_root = Path(args.repo_root).resolve()
    scope = getattr(args, "get_scope", None)
    include_sources = bool(getattr(args, "get_source", False))
    force_resolved = bool(getattr(args, "get_resolved", False))
    parts = getattr(args, "parts", []) or []
    session.record_effect(EffectClass.READ_ONLY, "read runtime settings")

    raw_key = " ".join(parts).strip() if parts else None
    selected_keys, key_error = _select_keys(raw_key)
    if key_error:
        return _error(args, request, key_error)
    selected_keys = selected_keys or list(ALL_KEYS)

    uncertainty: list[str] = []
    sections: dict[str, object]

    if scope and not force_resolved:
        scoped_values, normalization, warnings, origin = load_runtime_scope(scope, repo_root)
        uncertainty.extend(warnings)
        filtered = {key: scoped_values.get(key) for key in selected_keys if key in scoped_values}
        sections = {
            "settings": {
                "mode": "scope",
                "scope": scope,
                "origin": origin,
                "current": filtered,
                "aliases_applied": normalization,
            }
        }
        summary = f"Loaded {len(filtered)} runtime setting(s) from scope '{scope}'."
    else:
        resolution = resolve_runtime_settings(repo_root=repo_root, args=args, explicit_cli_values={})
        current = {key: resolution.values.get(key) for key in selected_keys}
        settings = {
            "mode": "resolved",
            "current": current,
            "aliases_applied": resolution.normalization,
        }
        if include_sources:
            settings["sources"] = {key: resolution.sources.get(key) for key in selected_keys}
        sections = {"settings": settings}
        uncertainty.extend(resolution.warnings)
        summary = f"Resolved {len(current)} runtime setting(s)."

    contract = _contract(
        request,
        summary=summary,
        next_step="Run: forge set <key> <value>",
        sections=sections,
        uncertainty=uncertainty,
    )
    if args.output_format == "json":
        emit_contract_json(contract)
        return 0
    return _render_text(args, contract, "=== FORGE GET ===")

"""Framework source-profile loading for optional framework-aware retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli

from core.capability_model import EffectClass
from core.effects import ExecutionSession


@dataclass(frozen=True)
class FrameworkProfile:
    profile_id: str
    version: str | None
    label: str | None
    aliases: list[str]
    framework_roots: list[Path]
    framework_docs_roots: list[Path]
    exclude_globs: list[str]
    retrieval_scope: str | None
    docs_allowlist_hosts: list[str] = field(default_factory=list)
    docs_entrypoints: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FrameworkRegistry:
    config_path: Path
    exists: bool
    default_profile: str | None
    profiles: dict[str, FrameworkProfile]
    alias_to_profile: dict[str, str]
    warnings: list[str]


def _normalize_alias(value: str) -> str:
    return value.strip().lower()


def _normalize_profile_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    profile_id = value.strip().lower()
    if not profile_id:
        return None
    return profile_id


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized:
            result.append(normalized)
    return result


def _path_list(raw_items: list[str], *, base_root: Path) -> list[Path]:
    resolved: list[Path] = []
    for item in raw_items:
        candidate = Path(item).expanduser()
        if candidate.is_absolute():
            resolved.append(candidate.resolve())
        else:
            resolved.append((base_root / candidate).resolve())
    return resolved


def load_framework_registry(repo_root: Path, session: ExecutionSession) -> FrameworkRegistry:
    config_path = repo_root / ".forge" / "frameworks.toml"
    if not config_path.exists():
        return FrameworkRegistry(
            config_path=config_path,
            exists=False,
            default_profile=None,
            profiles={},
            alias_to_profile={},
            warnings=[],
        )

    session.record_effect(EffectClass.READ_ONLY, f"read framework profiles {config_path}")
    try:
        payload = tomli.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomli.TOMLDecodeError) as exc:
        return FrameworkRegistry(
            config_path=config_path,
            exists=True,
            default_profile=None,
            profiles={},
            alias_to_profile={},
            warnings=[f"framework profiles config invalid: {exc}"],
        )

    warnings: list[str] = []
    default_profile_raw = payload.get("default_profile")
    default_profile = _normalize_profile_id(default_profile_raw)

    raw_profiles = payload.get("profiles")
    if not isinstance(raw_profiles, list):
        raw_profiles = payload.get("frameworks")
    if not isinstance(raw_profiles, list):
        raw_profiles = []

    profiles: dict[str, FrameworkProfile] = {}
    alias_to_profile: dict[str, str] = {}
    for idx, item in enumerate(raw_profiles, start=1):
        if not isinstance(item, dict):
            warnings.append(f"profile entry #{idx} ignored (not a table)")
            continue
        profile_id = _normalize_profile_id(item.get("id"))
        if profile_id is None:
            warnings.append(f"profile entry #{idx} ignored (missing id)")
            continue

        version = item.get("version")
        label = item.get("label")
        aliases = [_normalize_alias(alias) for alias in _string_list(item.get("aliases"))]
        local_paths = item.get("local_paths")
        local_paths_payload = local_paths if isinstance(local_paths, dict) else {}
        framework_roots = _path_list(_string_list(local_paths_payload.get("framework_roots")), base_root=repo_root)
        framework_docs_roots = _path_list(
            _string_list(local_paths_payload.get("framework_docs_roots")),
            base_root=repo_root,
        )
        exclude_globs = _string_list(local_paths_payload.get("exclude_globs"))

        retrieval_defaults = item.get("retrieval_defaults")
        retrieval_payload = retrieval_defaults if isinstance(retrieval_defaults, dict) else {}
        retrieval_scope = retrieval_payload.get("scope")
        if isinstance(retrieval_scope, str):
            retrieval_scope = retrieval_scope.strip().lower() or None
        else:
            retrieval_scope = None

        docs_cfg = item.get("docs")
        docs_payload = docs_cfg if isinstance(docs_cfg, dict) else {}
        docs_allowlist_hosts = [host.strip().lower() for host in _string_list(docs_payload.get("allowlist_hosts"))]
        docs_entrypoints = _string_list(docs_payload.get("entrypoints"))

        profile = FrameworkProfile(
            profile_id=profile_id,
            version=version.strip() if isinstance(version, str) and version.strip() else None,
            label=label.strip() if isinstance(label, str) and label.strip() else None,
            aliases=aliases,
            framework_roots=framework_roots,
            framework_docs_roots=framework_docs_roots,
            exclude_globs=exclude_globs,
            retrieval_scope=retrieval_scope,
            docs_allowlist_hosts=docs_allowlist_hosts,
            docs_entrypoints=docs_entrypoints,
        )
        profiles[profile_id] = profile
        alias_to_profile[profile_id] = profile_id
        for alias in aliases:
            if alias in alias_to_profile and alias_to_profile[alias] != profile_id:
                warnings.append(
                    f"alias '{alias}' mapped to multiple profiles; using '{alias_to_profile[alias]}'"
                )
                continue
            alias_to_profile[alias] = profile_id

    if default_profile and default_profile not in profiles:
        warnings.append(f"default_profile '{default_profile}' not found")
        default_profile = None

    return FrameworkRegistry(
        config_path=config_path,
        exists=True,
        default_profile=default_profile,
        profiles=profiles,
        alias_to_profile=alias_to_profile,
        warnings=warnings,
    )


def select_framework_profile(
    registry: FrameworkRegistry,
    requested: str | None,
) -> tuple[FrameworkProfile | None, str | None, list[str]]:
    warnings = list(registry.warnings)
    requested_norm = _normalize_profile_id(requested) if isinstance(requested, str) else None
    if not registry.exists:
        if requested_norm:
            warnings.append("framework profile requested but .forge/frameworks.toml is missing")
        return None, None, warnings

    resolved_id: str | None = None
    if requested_norm:
        resolved_id = registry.alias_to_profile.get(requested_norm)
        if resolved_id is None:
            warnings.append(f"framework profile '{requested_norm}' not found")
            return None, None, warnings
    elif registry.default_profile:
        resolved_id = registry.default_profile
    elif len(registry.profiles) == 1:
        resolved_id = next(iter(registry.profiles))

    if resolved_id is None:
        return None, None, warnings

    profile = registry.profiles.get(resolved_id)
    if profile is None:
        warnings.append(f"resolved framework profile '{resolved_id}' is missing")
        return None, None, warnings
    return profile, resolved_id, warnings

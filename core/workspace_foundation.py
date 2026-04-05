"""Repository/workspace foundation models and context resolution."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

WORKSPACE_CONTRACT_VERSION = "12.1"

RULE_PRIORITY_DEFAULT = 100
RULE_PRIORITY_REPO = 200
RULE_PRIORITY_LOCAL = 300
RULE_PRIORITY_CLI = 400

RULE_SOURCE_DEFAULT = "default"
RULE_SOURCE_REPO = "repo"
RULE_SOURCE_LOCAL = "local"
RULE_SOURCE_CLI = "cli"

LOCATOR_KIND_PATH = "path"
LOCATOR_KIND_URL = "url"
LOCATOR_KIND_VIRTUAL = "virtual"

ROLE_SOURCE_PATTERN = "pattern"
ROLE_SOURCE_SCOPE = "scope"
ROLE_SOURCE_KIND = "kind"

DECISION_ALLOW = "allow"
DECISION_DENY = "deny"

CASE_POLICY_SENSITIVE = "sensitive"
CASE_POLICY_INSENSITIVE = "insensitive"
WORKSPACE_STATUS_OK = "ok"
WORKSPACE_STATUS_PARTIAL = "partial"
WORKSPACE_STATUS_BLOCKED = "blocked"


@dataclass(frozen=True)
class ScopeDiagnostic:
    code: str
    message: str
    locator: str | None = None
    rule_id: str | None = None
    rule_source: str | None = None
    rule_priority: int | None = None


@dataclass(frozen=True)
class WorkspaceRule:
    rule_id: str
    rule_source: str
    rule_priority: int
    decision: str
    pattern: str


@dataclass(frozen=True)
class WorkspaceScope:
    root: str


@dataclass(frozen=True)
class WorkspaceContext:
    workspace_id: str
    workspace_contract_version: str
    workspace_snapshot_id: str
    workspace_status: str
    workspace_root: str
    repo_roots: tuple[str, ...]
    artifact_roots: tuple[str, ...]
    read_scopes: tuple[WorkspaceScope, ...]
    write_scopes: tuple[WorkspaceScope, ...]
    include_rules: tuple[WorkspaceRule, ...]
    ignore_rules: tuple[WorkspaceRule, ...]
    diagnostics: tuple[ScopeDiagnostic, ...]
    allow_symlinks: bool
    platform_case_policy: str


@dataclass(frozen=True)
class CanonicalLocator:
    locator: str
    locator_kind: str
    workspace_relative_path: str | None
    platform_case_policy: str


@dataclass(frozen=True)
class ScopeDecision:
    allowed: bool
    decision_type: str
    matched_rule_source: str | None
    matched_rule_id: str | None
    # Transitional compatibility fields for existing callers.
    # Keep until downstream foundations are migrated to matched_rule_* only.
    decision: str
    rule_id: str | None
    reason_code: str
    policy_relevant: bool
    diagnostics: tuple[ScopeDiagnostic, ...]


@dataclass(frozen=True)
class FileRoleAssignment:
    role: str
    role_source: str
    diagnostics: tuple[ScopeDiagnostic, ...] = tuple()


@dataclass(frozen=True)
class _RuleSpec:
    source: str
    priority: int
    decision: str
    patterns: tuple[str, ...]


def _extract_args_map(args: Any) -> Mapping[str, Any]:
    if args is None:
        return {}
    if isinstance(args, Mapping):
        return args
    if hasattr(args, "__dict__"):
        return vars(args)
    return {}


def _to_abs_posix(path_value: str, workspace_root: str) -> str:
    path = Path(path_value)
    if not path.is_absolute():
        path = Path(workspace_root) / path
    return path.resolve().as_posix()


def _normalize_scope_list(items: Sequence[str] | None, workspace_root: str) -> tuple[WorkspaceScope, ...]:
    if not items:
        return tuple()
    seen: set[str] = set()
    scopes: list[WorkspaceScope] = []
    for raw in items:
        root = _to_abs_posix(str(raw), workspace_root)
        if root in seen:
            continue
        seen.add(root)
        scopes.append(WorkspaceScope(root=root))
    return tuple(scopes)


def _normalize_patterns(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return tuple()
    if isinstance(raw, str):
        value = raw.strip()
        return (value,) if value else tuple()

    values: list[str] = []
    for item in raw:
        value = str(item).strip()
        if value:
            values.append(value)
    return tuple(values)


def _build_rules(rule_specs: Sequence[_RuleSpec]) -> tuple[WorkspaceRule, ...]:
    rules: list[WorkspaceRule] = []
    for spec in rule_specs:
        for idx, pattern in enumerate(spec.patterns):
            rules.append(
                WorkspaceRule(
                    rule_id=f"{spec.source}:{spec.decision}:{idx}",
                    rule_source=spec.source,
                    rule_priority=spec.priority,
                    decision=spec.decision,
                    pattern=pattern,
                )
            )
    return tuple(rules)


def _default_case_policy() -> str:
    if os.name == "nt":
        return CASE_POLICY_INSENSITIVE
    return CASE_POLICY_SENSITIVE


def compute_workspace_snapshot_id(workspace: WorkspaceContext) -> str:
    payload = {
        "workspace_id": workspace.workspace_id,
        "workspace_contract_version": workspace.workspace_contract_version,
        "workspace_root": workspace.workspace_root,
        "repo_roots": sorted(workspace.repo_roots),
        "artifact_roots": sorted(workspace.artifact_roots),
        "read_scopes": sorted(scope.root for scope in workspace.read_scopes),
        "write_scopes": sorted(scope.root for scope in workspace.write_scopes),
        "include_rules": sorted(
            (
                rule.rule_id,
                rule.rule_source,
                rule.rule_priority,
                rule.decision,
                rule.pattern,
            )
            for rule in workspace.include_rules
        ),
        "ignore_rules": sorted(
            (
                rule.rule_id,
                rule.rule_source,
                rule.rule_priority,
                rule.decision,
                rule.pattern,
            )
            for rule in workspace.ignore_rules
        ),
        "allow_symlinks": workspace.allow_symlinks,
        "platform_case_policy": workspace.platform_case_policy,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resolve_workspace_context(args: Any, repo_root: str | Path) -> WorkspaceContext:
    arg_map = _extract_args_map(args)

    normalized_repo_root = Path(repo_root).resolve().as_posix()
    workspace_root_raw = arg_map.get("workspace_root") or normalized_repo_root
    workspace_root = _to_abs_posix(str(workspace_root_raw), normalized_repo_root)

    repo_roots_raw = _normalize_patterns(arg_map.get("repo_roots")) or (normalized_repo_root,)
    repo_roots = tuple(dict.fromkeys(_to_abs_posix(item, workspace_root) for item in repo_roots_raw))

    artifact_roots_raw = _normalize_patterns(arg_map.get("artifact_roots"))
    artifact_roots = tuple(
        dict.fromkeys(
            [
                _to_abs_posix(str(Path(workspace_root) / ".forge"), workspace_root),
                *(_to_abs_posix(item, workspace_root) for item in artifact_roots_raw),
            ]
        )
    )

    read_scopes = _normalize_scope_list(arg_map.get("read_scopes"), workspace_root)
    if not read_scopes:
        read_scopes = (WorkspaceScope(root=workspace_root),)

    write_scopes = _normalize_scope_list(arg_map.get("write_scopes"), workspace_root)

    default_include = _normalize_patterns(arg_map.get("include_default")) or ("**",)
    default_ignore = _normalize_patterns(arg_map.get("ignore_default")) or (
        ".git/**",
        ".forge/**",
        "node_modules/**",
        "vendor/**",
        "dist/**",
        "build/**",
        "tmp/**",
        ".cache/**",
        "__pycache__/**",
        "*.pyc",
    )

    include_rules = _build_rules(
        [
            _RuleSpec(
                source=RULE_SOURCE_DEFAULT,
                priority=RULE_PRIORITY_DEFAULT,
                decision="include",
                patterns=default_include,
            ),
            _RuleSpec(
                source=RULE_SOURCE_REPO,
                priority=RULE_PRIORITY_REPO,
                decision="include",
                patterns=_normalize_patterns(arg_map.get("include_repo")),
            ),
            _RuleSpec(
                source=RULE_SOURCE_LOCAL,
                priority=RULE_PRIORITY_LOCAL,
                decision="include",
                patterns=_normalize_patterns(arg_map.get("include_local")),
            ),
            _RuleSpec(
                source=RULE_SOURCE_CLI,
                priority=RULE_PRIORITY_CLI,
                decision="include",
                patterns=_normalize_patterns(arg_map.get("include_cli")),
            ),
        ]
    )

    ignore_rules = _build_rules(
        [
            _RuleSpec(
                source=RULE_SOURCE_DEFAULT,
                priority=RULE_PRIORITY_DEFAULT,
                decision="ignore",
                patterns=default_ignore,
            ),
            _RuleSpec(
                source=RULE_SOURCE_REPO,
                priority=RULE_PRIORITY_REPO,
                decision="ignore",
                patterns=_normalize_patterns(arg_map.get("ignore_repo")),
            ),
            _RuleSpec(
                source=RULE_SOURCE_LOCAL,
                priority=RULE_PRIORITY_LOCAL,
                decision="ignore",
                patterns=_normalize_patterns(arg_map.get("ignore_local")),
            ),
            _RuleSpec(
                source=RULE_SOURCE_CLI,
                priority=RULE_PRIORITY_CLI,
                decision="ignore",
                patterns=_normalize_patterns(arg_map.get("ignore_cli")),
            ),
        ]
    )

    allow_symlinks = bool(arg_map.get("allow_symlinks", False))
    case_policy = str(arg_map.get("platform_case_policy") or _default_case_policy())

    workspace_id = f"workspace:{workspace_root}"
    diagnostics: list[ScopeDiagnostic] = []

    if case_policy not in (CASE_POLICY_SENSITIVE, CASE_POLICY_INSENSITIVE):
        diagnostics.append(
            ScopeDiagnostic(
                code="invalid_platform_case_policy",
                message="Invalid case policy; fallback to sensitive applied.",
            )
        )
        case_policy = CASE_POLICY_SENSITIVE

    read_scope_roots = tuple(scope.root for scope in read_scopes)
    for scope in write_scopes:
        if not any(scope.root == read_root or scope.root.startswith(f"{read_root}/") for read_root in read_scope_roots):
            diagnostics.append(
                ScopeDiagnostic(
                    code="write_scope_outside_read_scope",
                    message="Write scope must be within read scopes.",
                    locator=scope.root,
                )
            )

    workspace_status = WORKSPACE_STATUS_OK
    if any(diagnostic.code == "write_scope_outside_read_scope" for diagnostic in diagnostics):
        workspace_status = WORKSPACE_STATUS_BLOCKED
    elif diagnostics:
        workspace_status = WORKSPACE_STATUS_PARTIAL

    provisional = WorkspaceContext(
        workspace_id=workspace_id,
        workspace_contract_version=WORKSPACE_CONTRACT_VERSION,
        workspace_snapshot_id="",
        workspace_status=workspace_status,
        workspace_root=workspace_root,
        repo_roots=repo_roots,
        artifact_roots=artifact_roots,
        read_scopes=read_scopes,
        write_scopes=write_scopes,
        include_rules=include_rules,
        ignore_rules=ignore_rules,
        diagnostics=tuple(diagnostics),
        allow_symlinks=allow_symlinks,
        platform_case_policy=case_policy,
    )

    snapshot_id = compute_workspace_snapshot_id(provisional)
    return WorkspaceContext(
        workspace_id=provisional.workspace_id,
        workspace_contract_version=provisional.workspace_contract_version,
        workspace_snapshot_id=snapshot_id,
        workspace_status=provisional.workspace_status,
        workspace_root=provisional.workspace_root,
        repo_roots=provisional.repo_roots,
        artifact_roots=provisional.artifact_roots,
        read_scopes=provisional.read_scopes,
        write_scopes=provisional.write_scopes,
        include_rules=provisional.include_rules,
        ignore_rules=provisional.ignore_rules,
        diagnostics=provisional.diagnostics,
        allow_symlinks=provisional.allow_symlinks,
        platform_case_policy=provisional.platform_case_policy,
    )


from core.workspace_locators import normalize_locator
from core.workspace_roles import classify_file_role
from core.workspace_scope_rules import is_in_read_scope, is_in_write_scope

__all__ = [
    "CASE_POLICY_INSENSITIVE",
    "CASE_POLICY_SENSITIVE",
    "CanonicalLocator",
    "DECISION_ALLOW",
    "DECISION_DENY",
    "FileRoleAssignment",
    "LOCATOR_KIND_PATH",
    "LOCATOR_KIND_URL",
    "LOCATOR_KIND_VIRTUAL",
    "ROLE_SOURCE_KIND",
    "ROLE_SOURCE_PATTERN",
    "ROLE_SOURCE_SCOPE",
    "ScopeDecision",
    "ScopeDiagnostic",
    "WORKSPACE_CONTRACT_VERSION",
    "WORKSPACE_STATUS_BLOCKED",
    "WORKSPACE_STATUS_OK",
    "WORKSPACE_STATUS_PARTIAL",
    "WorkspaceContext",
    "WorkspaceRule",
    "WorkspaceScope",
    "classify_file_role",
    "compute_workspace_snapshot_id",
    "is_in_read_scope",
    "is_in_write_scope",
    "normalize_locator",
    "resolve_workspace_context",
]

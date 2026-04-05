"""File role classification for workspace locators."""

from __future__ import annotations

from pathlib import PurePosixPath

from core.workspace_foundation import (
    LOCATOR_KIND_PATH,
    ROLE_SOURCE_KIND,
    ROLE_SOURCE_PATTERN,
    ROLE_SOURCE_SCOPE,
    CanonicalLocator,
    FileRoleAssignment,
    ScopeDiagnostic,
    WorkspaceContext,
)


def _matches(relative_path: str, pattern: str) -> bool:
    normalized_pattern = pattern.strip().lstrip("./")
    rel = relative_path.strip().lstrip("./")
    if not normalized_pattern:
        return False
    if normalized_pattern == "**":
        return True
    if normalized_pattern.endswith("/**"):
        prefix = normalized_pattern[:-3].rstrip("/")
        return rel == prefix or rel.startswith(f"{prefix}/")

    path = PurePosixPath(rel)
    if path.match(normalized_pattern):
        return True
    if "/" not in normalized_pattern:
        return path.name == normalized_pattern
    return False


def _normalize_case(value: str, case_policy: str) -> str:
    if case_policy == "insensitive":
        return value.lower()
    return value


def _is_in_artifact_root(locator: CanonicalLocator, workspace: WorkspaceContext) -> bool:
    if locator.workspace_relative_path is None:
        return False
    absolute = _normalize_case(locator.locator, workspace.platform_case_policy)
    return any(
        absolute == _normalize_case(root, workspace.platform_case_policy)
        or absolute.startswith(f"{_normalize_case(root, workspace.platform_case_policy)}/")
        for root in workspace.artifact_roots
    )


def classify_file_role(locator: CanonicalLocator, workspace: WorkspaceContext) -> FileRoleAssignment:
    if locator.locator_kind != LOCATOR_KIND_PATH:
        return FileRoleAssignment(role="external", role_source=ROLE_SOURCE_KIND)

    if locator.workspace_relative_path is None:
        return FileRoleAssignment(role="external", role_source=ROLE_SOURCE_SCOPE)

    rel = _normalize_case(locator.workspace_relative_path, workspace.platform_case_policy)
    lower_rel = rel.lower()
    role_candidates: list[tuple[str, str, str]] = []

    if _is_in_artifact_root(locator, workspace):
        role_candidates.append(("artifact", ROLE_SOURCE_SCOPE, "artifact_root"))

    config_patterns = (
        ".forge/**",
        ".github/**",
        "*.toml",
        "*.yaml",
        "*.yml",
        "*.json",
        "*.ini",
        "*.cfg",
    )
    for pattern in config_patterns:
        if _matches(rel, pattern):
            role_candidates.append(("config", ROLE_SOURCE_PATTERN, pattern))
            break

    test_patterns = (
        "tests/**",
        "test/**",
        "*_test.py",
        "test_*.py",
        "*.spec.ts",
        "*.test.ts",
        "*.spec.js",
        "*.test.js",
    )
    for pattern in test_patterns:
        if _matches(rel, pattern):
            role_candidates.append(("test", ROLE_SOURCE_PATTERN, pattern))
            break

    docs_patterns = (
        "docs/**",
        "*.md",
        "*.rst",
        "*.adoc",
    )
    for pattern in docs_patterns:
        if _matches(rel, pattern):
            role_candidates.append(("docs", ROLE_SOURCE_PATTERN, pattern))
            break

    generated_patterns = (
        "node_modules/**",
        "vendor/**",
        "dist/**",
        "build/**",
        "coverage/**",
        "*.min.js",
        "*.map",
        "*.pyc",
        "__pycache__/**",
    )
    for pattern in generated_patterns:
        if _matches(rel, pattern):
            role_candidates.append(("generated", ROLE_SOURCE_PATTERN, pattern))
            break

    if lower_rel.startswith("tmp/") or lower_rel.startswith("temp/"):
        role_candidates.append(("artifact", ROLE_SOURCE_PATTERN, "temp_prefix"))

    if not role_candidates:
        return FileRoleAssignment(role="source", role_source=ROLE_SOURCE_PATTERN)

    primary_role, primary_source, primary_origin = role_candidates[0]
    distinct_roles = sorted({role for role, _source, _origin in role_candidates})
    if len(distinct_roles) == 1:
        return FileRoleAssignment(role=primary_role, role_source=primary_source)

    alternatives = ",".join(role for role in distinct_roles if role != primary_role)
    diagnostic = ScopeDiagnostic(
        code="multiple_role_matches",
        message=f"Multiple role patterns matched. selected={primary_role}; alternatives={alternatives}",
        locator=locator.locator,
        rule_id=f"role:{primary_role}",
        rule_source=primary_origin,
    )
    return FileRoleAssignment(
        role=primary_role,
        role_source=primary_source,
        diagnostics=(diagnostic,),
    )

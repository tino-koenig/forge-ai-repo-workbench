"""Canonical locator normalization for workspace-scoped references."""

from __future__ import annotations

import os
from pathlib import Path

from core.workspace_foundation import (
    LOCATOR_KIND_PATH,
    LOCATOR_KIND_URL,
    LOCATOR_KIND_VIRTUAL,
    CanonicalLocator,
    WorkspaceContext,
)


_URL_PREFIXES = ("http://", "https://", "ssh://", "git://")
_VIRTUAL_PREFIXES = ("virtual:", "mem://", "forge://")


def _is_url(value: str) -> bool:
    return value.startswith(_URL_PREFIXES)


def _is_virtual(value: str) -> bool:
    return value.startswith(_VIRTUAL_PREFIXES)


def normalize_locator(path_or_ref: str, workspace: WorkspaceContext) -> CanonicalLocator:
    raw = str(path_or_ref).strip()
    if _is_url(raw):
        return CanonicalLocator(
            locator=raw,
            locator_kind=LOCATOR_KIND_URL,
            workspace_relative_path=None,
            platform_case_policy=workspace.platform_case_policy,
        )

    if _is_virtual(raw):
        return CanonicalLocator(
            locator=raw,
            locator_kind=LOCATOR_KIND_VIRTUAL,
            workspace_relative_path=None,
            platform_case_policy=workspace.platform_case_policy,
        )

    path = Path(raw)
    if not path.is_absolute():
        path = Path(workspace.workspace_root) / path

    # Keep locator and workspace_relative_path derived from the same lexical
    # normalization so both fields always describe the same path identity.
    # Symlink policy is enforced by scope rules, not by locator rewriting.
    lexical_path = Path(os.path.normpath(str(path.absolute())))
    canonical_path = lexical_path.as_posix()
    workspace_relative_path: str | None = None

    try:
        workspace_relative_path = lexical_path.relative_to(Path(workspace.workspace_root)).as_posix()
    except ValueError:
        workspace_relative_path = None

    return CanonicalLocator(
        locator=canonical_path,
        locator_kind=LOCATOR_KIND_PATH,
        workspace_relative_path=workspace_relative_path,
        platform_case_policy=workspace.platform_case_policy,
    )

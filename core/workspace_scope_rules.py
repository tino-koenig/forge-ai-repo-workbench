"""Read/write scope decisions for canonical workspace locators."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from core.workspace_foundation import (
    DECISION_ALLOW,
    DECISION_DENY,
    LOCATOR_KIND_PATH,
    CanonicalLocator,
    ScopeDecision,
    ScopeDiagnostic,
    WorkspaceContext,
    WorkspaceRule,
)


def _normalize_case(value: str, case_policy: str) -> str:
    if case_policy == "insensitive":
        return value.lower()
    return value


def _matches_rule(relative_path: str, rule: WorkspaceRule, case_policy: str) -> bool:
    pattern = rule.pattern.strip().lstrip("./")
    rel = relative_path.strip().lstrip("./")
    pattern = _normalize_case(pattern, case_policy)
    rel = _normalize_case(rel, case_policy)
    if not pattern:
        return False
    if pattern == "**":
        return True
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return rel == prefix or rel.startswith(f"{prefix}/")

    if "/" not in pattern:
        return PurePosixPath(rel).name == pattern or PurePosixPath(rel).match(pattern)

    path = PurePosixPath(rel)
    if path.match(pattern):
        return True
    return False


def _evaluate_include_ignore(
    locator: CanonicalLocator,
    workspace: WorkspaceContext,
) -> tuple[bool, WorkspaceRule | None, tuple[ScopeDiagnostic, ...]]:
    if locator.workspace_relative_path is None:
        return False, None, (
            ScopeDiagnostic(
                code="outside_workspace",
                message="Path is outside workspace root and cannot be included.",
                locator=locator.locator,
            ),
        )

    rel = locator.workspace_relative_path
    include_matches = [
        rule for rule in workspace.include_rules if _matches_rule(rel, rule, workspace.platform_case_policy)
    ]
    ignore_matches = [
        rule for rule in workspace.ignore_rules if _matches_rule(rel, rule, workspace.platform_case_policy)
    ]

    diagnostics: list[ScopeDiagnostic] = []
    if include_matches and ignore_matches:
        top_include = max(include_matches, key=_rule_rank)
        top_ignore = max(ignore_matches, key=_rule_rank)
        winner = max((top_include, top_ignore), key=_rule_rank)
        loser = top_ignore if winner is top_include else top_include
        diagnostics.append(
            ScopeDiagnostic(
                code="scope_rule_conflict_resolved",
                message="Include/ignore conflict resolved by rule priority.",
                locator=locator.locator,
                rule_id=winner.rule_id,
                rule_source=winner.rule_source,
                rule_priority=winner.rule_priority,
            )
        )
        diagnostics.append(
            ScopeDiagnostic(
                code="scope_rule_conflict_loser",
                message="Losing rule for include/ignore conflict resolution.",
                locator=locator.locator,
                rule_id=loser.rule_id,
                rule_source=loser.rule_source,
                rule_priority=loser.rule_priority,
            )
        )
        return winner.decision == "include", winner, tuple(diagnostics)

    if ignore_matches:
        winner = max(ignore_matches, key=_rule_rank)
        diagnostics.append(
            ScopeDiagnostic(
                code="ignored_by_rule",
                message="Path is blocked by ignore rule.",
                locator=locator.locator,
                rule_id=winner.rule_id,
                rule_source=winner.rule_source,
                rule_priority=winner.rule_priority,
            )
        )
        return False, winner, tuple(diagnostics)

    if include_matches:
        winner = max(include_matches, key=_rule_rank)
        return True, winner, tuple(diagnostics)

    diagnostics.append(
        ScopeDiagnostic(
            code="no_matching_include_rule",
            message="Path does not match any include rule.",
            locator=locator.locator,
        )
    )
    return False, None, tuple(diagnostics)


def _is_within_scopes(locator: CanonicalLocator, roots: tuple[str, ...], case_policy: str) -> bool:
    if locator.locator_kind != LOCATOR_KIND_PATH:
        return False
    target = Path(locator.locator)
    normalized_target = _normalize_case(target.as_posix(), case_policy).rstrip("/")
    for root in roots:
        normalized_root = _normalize_case(Path(root).as_posix(), case_policy).rstrip("/")
        if normalized_target == normalized_root or normalized_target.startswith(f"{normalized_root}/"):
            return True
    return False


def _build_scope_decision(
    decision_type: str,
    decision: str,
    reason_code: str,
    diagnostics: tuple[ScopeDiagnostic, ...],
    rule: WorkspaceRule | None = None,
    matched_rule_id: str | None = None,
    matched_rule_source: str | None = None,
) -> ScopeDecision:
    effective_rule_id = matched_rule_id if matched_rule_id is not None else (rule.rule_id if rule else None)
    effective_rule_source = (
        matched_rule_source if matched_rule_source is not None else (rule.rule_source if rule else None)
    )
    return ScopeDecision(
        allowed=decision == DECISION_ALLOW,
        decision_type=decision_type,
        matched_rule_source=effective_rule_source,
        matched_rule_id=effective_rule_id,
        decision=decision,
        rule_id=effective_rule_id,
        reason_code=reason_code,
        policy_relevant=decision != DECISION_ALLOW,
        diagnostics=diagnostics,
    )


def _rule_rank(rule: WorkspaceRule) -> tuple[int, int, str]:
    decision_weight = 1 if rule.decision == "ignore" else 0
    return (rule.rule_priority, decision_weight, rule.rule_id)


def _contains_symlink(locator: CanonicalLocator, workspace: WorkspaceContext) -> bool:
    if locator.workspace_relative_path is None:
        return False
    candidate = Path(workspace.workspace_root) / locator.workspace_relative_path
    if not candidate.exists():
        return False

    cursor = Path(workspace.workspace_root)
    for part in Path(locator.workspace_relative_path).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            return True
    return False


def is_in_read_scope(locator: CanonicalLocator, workspace: WorkspaceContext) -> ScopeDecision:
    if locator.locator_kind != LOCATOR_KIND_PATH:
        diagnostic = ScopeDiagnostic(
            code="unsupported_locator_kind",
            message="Only path locators are eligible for read scope checks.",
            locator=locator.locator,
        )
        return _build_scope_decision(
            decision_type="read",
            decision=DECISION_DENY,
            reason_code="unsupported_locator_kind",
            diagnostics=(diagnostic,),
            rule=None,
        )

    if not workspace.allow_symlinks and _contains_symlink(locator, workspace):
        diagnostic = ScopeDiagnostic(
            code="symlink_not_allowed",
            message="Path crosses a symlink while symlink support is disabled.",
            locator=locator.locator,
        )
        return _build_scope_decision(
            decision_type="read",
            decision=DECISION_DENY,
            reason_code="symlink_not_allowed",
            diagnostics=(diagnostic,),
            rule=None,
        )

    included, rule, include_diag = _evaluate_include_ignore(locator, workspace)
    if not included:
        return _build_scope_decision(
            decision_type="read",
            decision=DECISION_DENY,
            reason_code=include_diag[0].code if include_diag else "not_included",
            diagnostics=include_diag,
            rule=rule,
        )

    scope_roots = tuple(scope.root for scope in workspace.read_scopes)
    if _is_within_scopes(locator, scope_roots, workspace.platform_case_policy):
        return _build_scope_decision(
            decision_type="read",
            decision=DECISION_ALLOW,
            reason_code="read_scope_match",
            diagnostics=include_diag,
            rule=rule,
        )

    diagnostic = ScopeDiagnostic(
        code="outside_read_scope",
        message="Path is outside allowed read scopes.",
        locator=locator.locator,
    )
    return _build_scope_decision(
        decision_type="read",
        decision=DECISION_DENY,
        reason_code="outside_read_scope",
        diagnostics=include_diag + (diagnostic,),
        rule=rule,
    )


def is_in_write_scope(locator: CanonicalLocator, workspace: WorkspaceContext) -> ScopeDecision:
    if workspace.workspace_status == "blocked":
        diagnostic = ScopeDiagnostic(
            code="workspace_blocked",
            message="Workspace context is blocked by invalid scope configuration.",
            locator=locator.locator,
        )
        return _build_scope_decision(
            decision_type="write",
            decision=DECISION_DENY,
            reason_code="workspace_blocked",
            diagnostics=workspace.diagnostics + (diagnostic,),
            rule=None,
        )

    read_decision = is_in_read_scope(locator, workspace)
    if read_decision.decision != DECISION_ALLOW:
        return _build_scope_decision(
            decision_type="write",
            decision=DECISION_DENY,
            reason_code="write_requires_read_scope",
            diagnostics=read_decision.diagnostics,
            matched_rule_id=read_decision.matched_rule_id,
            matched_rule_source=read_decision.matched_rule_source,
        )

    if not workspace.write_scopes:
        diagnostic = ScopeDiagnostic(
            code="write_scope_deny_by_default",
            message="No write scopes configured; write access is denied by default.",
            locator=locator.locator,
        )
        return _build_scope_decision(
            decision_type="write",
            decision=DECISION_DENY,
            reason_code="write_scope_deny_by_default",
            diagnostics=read_decision.diagnostics + (diagnostic,),
            matched_rule_id=read_decision.matched_rule_id,
            matched_rule_source=read_decision.matched_rule_source,
        )

    scope_roots = tuple(scope.root for scope in workspace.write_scopes)
    if _is_within_scopes(locator, scope_roots, workspace.platform_case_policy):
        return _build_scope_decision(
            decision_type="write",
            decision=DECISION_ALLOW,
            reason_code="write_scope_match",
            diagnostics=read_decision.diagnostics,
            matched_rule_id=read_decision.matched_rule_id,
            matched_rule_source=read_decision.matched_rule_source,
        )

    diagnostic = ScopeDiagnostic(
        code="outside_write_scope",
        message="Path is outside configured write scopes.",
        locator=locator.locator,
    )
    return _build_scope_decision(
        decision_type="write",
        decision=DECISION_DENY,
        reason_code="outside_write_scope",
        diagnostics=read_decision.diagnostics + (diagnostic,),
        matched_rule_id=read_decision.matched_rule_id,
        matched_rule_source=read_decision.matched_rule_source,
    )

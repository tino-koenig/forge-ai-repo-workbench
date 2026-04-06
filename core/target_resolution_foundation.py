"""Target Resolution Foundation (09): deterministic target resolution contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Literal, Mapping, Sequence

RESOLUTION_CONTRACT_VERSION = "09.1"

ResolutionStatus = Literal["resolved", "unresolved", "ambiguous", "blocked"]
ResolvedKind = Literal["path", "symbol", "directory", "repo"]
CandidateKind = Literal["path", "symbol", "directory", "repo"]
ResolutionSource = Literal["explicit_path", "symbol_match", "from_run", "fallback"]
ResolutionStrategy = Literal["exact", "policy_fallback", "best_effort_heuristic"]
TransitionStatus = Literal["allowed", "blocked"]
DiagnosticSeverity = Literal["info", "warning", "error"]

KIND_PRIORITY: Mapping[str, int] = {
    "path": 500,
    "symbol": 300,
    "directory": 200,
    "repo": 100,
}


@dataclass(frozen=True)
class TargetResolutionDiagnostic:
    code: str
    message: str
    severity: DiagnosticSeverity
    context: Mapping[str, object] | None = None


@dataclass(frozen=True)
class TargetCandidate:
    kind: CandidateKind
    path: str | None
    symbol: str | None
    resolution_priority: int
    rationale: str
    source: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        allowed = {"path", "symbol", "directory", "repo"}
        if self.kind not in allowed:
            raise ValueError(f"Unsupported candidate kind '{self.kind}'.")

    @property
    def normalized_target(self) -> str:
        if self.path:
            return self.path
        if self.symbol:
            return self.symbol
        return self.kind


@dataclass(frozen=True)
class TransitionDecision:
    status: TransitionStatus
    allowed: bool
    source_mode: str | None
    target_mode: str | None
    target_capability: str | None
    reason: str
    diagnostics: tuple[TargetResolutionDiagnostic, ...] = tuple()


@dataclass(frozen=True)
class TargetRequest:
    raw_target: str
    capability: str
    profile: str
    from_run: str | None = None
    constraints: Mapping[str, object] = field(default_factory=dict)
    target_hints: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolutionPolicy:
    ambiguity_top_k: int = 3
    allow_directory_fallback: bool = True
    allow_repo_fallback: bool = True
    unresolved_explicit_target_blocks_fallback: bool = False

    def __post_init__(self) -> None:
        if self.ambiguity_top_k < 1:
            raise ValueError("ambiguity_top_k must be >= 1.")


@dataclass(frozen=True)
class FromRunReference:
    run_id: str
    resolved_target: str
    resolved_kind: ResolvedKind
    resolved_path: str | None
    resolved_symbol: str | None
    source_capability: str
    source_mode: str
    strategy: ResolutionStrategy
    evidence_anchors: tuple[Mapping[str, object], ...] = tuple()
    transition_meta: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class TargetResolutionContext:
    candidate_pool: tuple[TargetCandidate, ...]
    known_paths: tuple[str, ...] = tuple()
    known_directories: tuple[str, ...] = tuple()
    repo_root: str | None = None
    from_run_references: Mapping[str, FromRunReference] = field(default_factory=dict)
    allowed_transitions: tuple[tuple[str, str], ...] = tuple()
    capability_mode_map: Mapping[str, str] = field(default_factory=dict)
    policy: ResolutionPolicy = field(default_factory=ResolutionPolicy)
    run_id: str | None = None
    trace_id: str | None = None
    workspace_snapshot_id: str | None = None


@dataclass(frozen=True)
class TargetResolutionResult:
    resolution_contract_version: str
    resolution_status: ResolutionStatus
    resolved_kind: ResolvedKind | None
    resolved_target: str | None
    resolved_path: str | None
    resolved_symbol: str | None
    resolution_source: ResolutionSource | None
    resolution_strategy: ResolutionStrategy | None
    candidates: tuple[TargetCandidate, ...]
    evidence_anchors: tuple[Mapping[str, object], ...]
    diagnostics: tuple[TargetResolutionDiagnostic, ...]
    ambiguity_top_k: tuple[TargetCandidate, ...]
    transition_meta: Mapping[str, object]
    run_id: str | None = None
    trace_id: str | None = None
    workspace_snapshot_id: str | None = None


def order_target_candidates_for_resolution(
    candidates: Sequence[TargetCandidate],
    policy: ResolutionPolicy,
) -> list[TargetCandidate]:
    del policy  # policy hook reserved for future policy-driven order shaping.
    return sorted(
        candidates,
        key=lambda item: (
            -item.resolution_priority,
            -KIND_PRIORITY.get(item.kind, 0),
            item.path or "",
            item.symbol or "",
            item.source,
            item.rationale,
        ),
    )


def validate_transition(
    source_mode: str,
    target_mode: str,
    context: TargetResolutionContext,
    *,
    target_capability: str | None = None,
) -> TransitionDecision:
    if (source_mode, target_mode) in set(context.allowed_transitions):
        return TransitionDecision(
            status="allowed",
            allowed=True,
            source_mode=source_mode,
            target_mode=target_mode,
            target_capability=target_capability,
            reason="transition_allowed",
        )
    return TransitionDecision(
        status="blocked",
        allowed=False,
        source_mode=source_mode,
        target_mode=target_mode,
        target_capability=target_capability,
        reason="transition_blocked",
        diagnostics=(
            TargetResolutionDiagnostic(
                code="transition_blocked",
                message=f"Transition {source_mode}->{target_mode} is not allowed.",
                severity="error",
                context={
                    "source_mode": source_mode,
                    "target_mode": target_mode,
                    "target_capability": target_capability,
                },
            ),
        ),
    )


def _resolve_target_mode(request: TargetRequest, context: TargetResolutionContext) -> str | None:
    constraint_mode = request.constraints.get("target_mode")
    if isinstance(constraint_mode, str) and constraint_mode.strip():
        return constraint_mode.strip()

    hint_mode = request.target_hints.get("target_mode")
    if isinstance(hint_mode, str) and hint_mode.strip():
        return hint_mode.strip()

    mapped_mode = context.capability_mode_map.get(request.capability)
    if isinstance(mapped_mode, str) and mapped_mode.strip():
        return mapped_mode.strip()

    default_mode_map = {
        "query": "query",
        "explain": "explain",
        "review": "review",
        "describe": "describe",
        "test": "test",
        "ask": "ask",
    }
    fallback_mode = default_mode_map.get(request.capability)
    if isinstance(fallback_mode, str) and fallback_mode.strip():
        return fallback_mode.strip()
    return None


def _explicit_path_result(
    request: TargetRequest, context: TargetResolutionContext
) -> TargetResolutionResult | None:
    raw = request.raw_target.strip()
    if not _is_explicit_path_target(raw, request, context):
        return None
    if not _kind_allowed("path", request) and not _kind_allowed("directory", request):
        return TargetResolutionResult(
            resolution_contract_version=RESOLUTION_CONTRACT_VERSION,
            resolution_status="blocked",
            resolved_kind=None,
            resolved_target=None,
            resolved_path=None,
            resolved_symbol=None,
            resolution_source="explicit_path",
            resolution_strategy="exact",
            candidates=tuple(),
            evidence_anchors=tuple(),
            diagnostics=(
                TargetResolutionDiagnostic(
                    code="constraint_blocks_path_resolution",
                    message="Path resolution blocked by constraints.allowed_candidate_kinds.",
                    severity="warning",
                    context={"allowed_candidate_kinds": _allowed_candidate_kinds(request)},
                ),
            ),
            ambiguity_top_k=tuple(),
            transition_meta={},
            run_id=context.run_id,
            trace_id=context.trace_id,
            workspace_snapshot_id=context.workspace_snapshot_id,
        )
    if raw in set(context.known_paths):
        return TargetResolutionResult(
            resolution_contract_version=RESOLUTION_CONTRACT_VERSION,
            resolution_status="resolved",
            resolved_kind="path",
            resolved_target=raw,
            resolved_path=raw,
            resolved_symbol=None,
            resolution_source="explicit_path",
            resolution_strategy="exact",
            candidates=tuple(),
            evidence_anchors=tuple(),
            diagnostics=tuple(),
            ambiguity_top_k=tuple(),
            transition_meta={},
            run_id=context.run_id,
            trace_id=context.trace_id,
            workspace_snapshot_id=context.workspace_snapshot_id,
        )
    if raw in set(context.known_directories):
        return TargetResolutionResult(
            resolution_contract_version=RESOLUTION_CONTRACT_VERSION,
            resolution_status="resolved",
            resolved_kind="directory",
            resolved_target=raw,
            resolved_path=raw,
            resolved_symbol=None,
            resolution_source="explicit_path",
            resolution_strategy="exact",
            candidates=tuple(),
            evidence_anchors=tuple(),
            diagnostics=tuple(),
            ambiguity_top_k=tuple(),
            transition_meta={},
            run_id=context.run_id,
            trace_id=context.trace_id,
            workspace_snapshot_id=context.workspace_snapshot_id,
        )
    return TargetResolutionResult(
        resolution_contract_version=RESOLUTION_CONTRACT_VERSION,
        resolution_status="unresolved",
        resolved_kind=None,
        resolved_target=None,
        resolved_path=None,
        resolved_symbol=None,
        resolution_source="explicit_path",
        resolution_strategy="exact",
        candidates=tuple(),
        evidence_anchors=tuple(),
        diagnostics=(
            TargetResolutionDiagnostic(
                code="unresolved_path",
                message=f"Explicit path '{raw}' could not be resolved.",
                severity="warning",
            ),
        ),
        ambiguity_top_k=tuple(),
        transition_meta={},
        run_id=context.run_id,
        trace_id=context.trace_id,
        workspace_snapshot_id=context.workspace_snapshot_id,
    )


def resolve_from_run_reference(request: TargetRequest, context: TargetResolutionContext) -> TargetResolutionResult:
    from_run_id = request.from_run or ""
    reference = context.from_run_references.get(from_run_id)
    if reference is None:
        return TargetResolutionResult(
            resolution_contract_version=RESOLUTION_CONTRACT_VERSION,
            resolution_status="unresolved",
            resolved_kind=None,
            resolved_target=None,
            resolved_path=None,
            resolved_symbol=None,
            resolution_source="from_run",
            resolution_strategy="exact",
            candidates=tuple(),
            evidence_anchors=tuple(),
            diagnostics=(
                TargetResolutionDiagnostic(
                    code="unresolved_from_run_reference",
                    message=f"from_run reference '{from_run_id}' not found.",
                    severity="warning",
                ),
            ),
            ambiguity_top_k=tuple(),
            transition_meta={"from_run": from_run_id},
            run_id=context.run_id,
            trace_id=context.trace_id,
            workspace_snapshot_id=context.workspace_snapshot_id,
        )

    target_mode = _resolve_target_mode(request, context)
    if target_mode is None:
        return TargetResolutionResult(
            resolution_contract_version=RESOLUTION_CONTRACT_VERSION,
            resolution_status="blocked",
            resolved_kind=None,
            resolved_target=None,
            resolved_path=None,
            resolved_symbol=None,
            resolution_source="from_run",
            resolution_strategy="exact",
            candidates=tuple(),
            evidence_anchors=tuple(reference.evidence_anchors),
            diagnostics=(
                TargetResolutionDiagnostic(
                    code="target_mode_unresolved",
                    message="Target mode is required for transition validation and could not be resolved.",
                    severity="error",
                    context={"target_capability": request.capability},
                ),
            ),
            ambiguity_top_k=tuple(),
            transition_meta={
                "from_run": reference.run_id,
                "source_mode": reference.source_mode,
                "target_mode": None,
                "target_capability": request.capability,
                "source_capability": reference.source_capability,
                "strategy": reference.strategy,
                **dict(reference.transition_meta),
            },
            run_id=context.run_id,
            trace_id=context.trace_id,
            workspace_snapshot_id=context.workspace_snapshot_id,
        )

    transition = validate_transition(
        reference.source_mode,
        target_mode,
        context,
        target_capability=request.capability,
    )
    if not transition.allowed:
        return TargetResolutionResult(
            resolution_contract_version=RESOLUTION_CONTRACT_VERSION,
            resolution_status="blocked",
            resolved_kind=None,
            resolved_target=None,
            resolved_path=None,
            resolved_symbol=None,
            resolution_source="from_run",
            resolution_strategy="exact",
            candidates=tuple(),
            evidence_anchors=tuple(reference.evidence_anchors),
            diagnostics=transition.diagnostics,
            ambiguity_top_k=tuple(),
            transition_meta={
                "from_run": reference.run_id,
                "source_mode": reference.source_mode,
                "target_mode": target_mode,
                "target_capability": request.capability,
                "source_capability": reference.source_capability,
                "strategy": reference.strategy,
                **dict(reference.transition_meta),
            },
            run_id=context.run_id,
            trace_id=context.trace_id,
            workspace_snapshot_id=context.workspace_snapshot_id,
        )

    return TargetResolutionResult(
        resolution_contract_version=RESOLUTION_CONTRACT_VERSION,
        resolution_status="resolved",
        resolved_kind=reference.resolved_kind,
        resolved_target=reference.resolved_target,
        resolved_path=reference.resolved_path,
        resolved_symbol=reference.resolved_symbol,
        resolution_source="from_run",
        resolution_strategy=reference.strategy,
        candidates=tuple(),
        evidence_anchors=tuple(reference.evidence_anchors),
        diagnostics=tuple(),
        ambiguity_top_k=tuple(),
        transition_meta={
            "from_run": reference.run_id,
            "source_mode": reference.source_mode,
            "target_mode": target_mode,
            "target_capability": request.capability,
            "source_capability": reference.source_capability,
            "strategy": reference.strategy,
            **dict(reference.transition_meta),
        },
        run_id=context.run_id,
        trace_id=context.trace_id,
        workspace_snapshot_id=context.workspace_snapshot_id,
    )


def _symbol_candidates(request: TargetRequest, context: TargetResolutionContext) -> tuple[TargetCandidate, ...]:
    if not _kind_allowed("symbol", request):
        return tuple()
    raw = request.raw_target.strip()
    candidates = [
        candidate
        for candidate in context.candidate_pool
        if candidate.symbol and candidate.symbol == raw
    ]
    candidates = _apply_target_hints_to_candidates(request, candidates)
    return tuple(order_target_candidates_for_resolution(candidates, context.policy))


def _fallback_candidates(request: TargetRequest, context: TargetResolutionContext) -> tuple[TargetCandidate, ...]:
    if not _fallback_allowed(request, context):
        return tuple()
    fallback: list[TargetCandidate] = []
    if context.policy.allow_directory_fallback and context.known_directories and _kind_allowed("directory", request):
        for directory in sorted(set(context.known_directories)):
            fallback.append(
                TargetCandidate(
                    kind="directory",
                    path=directory,
                    symbol=None,
                    resolution_priority=KIND_PRIORITY["directory"],
                    rationale="policy directory fallback candidate.",
                    source="fallback_policy",
                )
            )
    if context.policy.allow_repo_fallback and context.repo_root and _kind_allowed("repo", request):
        fallback.append(
            TargetCandidate(
                kind="repo",
                path=context.repo_root,
                symbol=None,
                resolution_priority=KIND_PRIORITY["repo"],
                rationale="policy repo fallback candidate.",
                source="fallback_policy",
            )
        )
    return tuple(order_target_candidates_for_resolution(fallback, context.policy))


def _is_explicit_path_target(raw: str, request: TargetRequest, context: TargetResolutionContext) -> bool:
    hint_kind = str(request.target_hints.get("target_kind", "")).strip().lower()
    if hint_kind == "path":
        return True
    if request.target_hints.get("is_path") is True:
        return True
    if raw in set(context.known_paths) or raw in set(context.known_directories):
        return True
    if raw.startswith(("/", "./", "../", "~", ".\\", "..\\", "\\")):
        return True
    if "/" in raw or "\\" in raw:
        return True
    if len(raw) >= 3 and raw[1] == ":" and raw[2] in ("\\", "/"):
        return True
    path = PurePosixPath(raw)
    suffix = path.suffix.lower()
    likely_file_suffixes = {".py", ".md", ".txt", ".toml", ".json", ".yaml", ".yml", ".js", ".ts"}
    if suffix in likely_file_suffixes:
        return True
    return False


def _allowed_candidate_kinds(request: TargetRequest) -> tuple[str, ...]:
    raw = request.constraints.get("allowed_candidate_kinds")
    if raw is None:
        return ("path", "symbol", "directory", "repo")
    values: tuple[str, ...]
    if isinstance(raw, str):
        values = (raw.strip(),)
    elif isinstance(raw, Sequence):
        values = tuple(str(item).strip() for item in raw)
    else:
        return ("path", "symbol", "directory", "repo")
    allowed = tuple(item for item in values if item in ("path", "symbol", "directory", "repo"))
    return allowed or ("path", "symbol", "directory", "repo")


def _kind_allowed(kind: str, request: TargetRequest) -> bool:
    return kind in _allowed_candidate_kinds(request)


def _fallback_allowed(request: TargetRequest, context: TargetResolutionContext) -> bool:
    override = request.constraints.get("allow_fallback")
    if isinstance(override, bool):
        return override
    return context.policy.allow_directory_fallback or context.policy.allow_repo_fallback


def _apply_target_hints_to_candidates(
    request: TargetRequest,
    candidates: Sequence[TargetCandidate],
) -> list[TargetCandidate]:
    preferred_prefix = str(request.target_hints.get("preferred_path_prefix", "")).strip()
    if not preferred_prefix:
        return list(candidates)
    adjusted: list[TargetCandidate] = []
    for candidate in candidates:
        if candidate.path and candidate.path.startswith(preferred_prefix):
            adjusted.append(
                TargetCandidate(
                    kind=candidate.kind,
                    path=candidate.path,
                    symbol=candidate.symbol,
                    resolution_priority=candidate.resolution_priority + 25,
                    rationale=f"{candidate.rationale} preferred_path_prefix matched",
                    source=candidate.source,
                    metadata=dict(candidate.metadata),
                )
            )
        else:
            adjusted.append(candidate)
    return adjusted


def _resolved_result_from_candidate(
    candidate: TargetCandidate,
    request: TargetRequest,
    context: TargetResolutionContext,
    *,
    resolution_source: ResolutionSource,
    resolution_strategy: ResolutionStrategy,
    candidates: Sequence[TargetCandidate],
    diagnostics: Sequence[TargetResolutionDiagnostic] = tuple(),
) -> TargetResolutionResult:
    resolved_kind = candidate.kind
    resolved_path = candidate.path
    resolved_symbol = candidate.symbol
    resolved_target = candidate.normalized_target
    raw_anchors = candidate.metadata.get("evidence_anchors", tuple())
    anchors: tuple[Mapping[str, object], ...] = tuple()
    if isinstance(raw_anchors, Sequence):
        anchors = tuple(anchor for anchor in raw_anchors if isinstance(anchor, Mapping))
    return TargetResolutionResult(
        resolution_contract_version=RESOLUTION_CONTRACT_VERSION,
        resolution_status="resolved",
        resolved_kind=resolved_kind,
        resolved_target=resolved_target,
        resolved_path=resolved_path,
        resolved_symbol=resolved_symbol,
        resolution_source=resolution_source,
        resolution_strategy=resolution_strategy,
        candidates=tuple(candidates),
        evidence_anchors=anchors,
        diagnostics=tuple(diagnostics),
        ambiguity_top_k=tuple(),
        transition_meta={},
        run_id=context.run_id,
        trace_id=context.trace_id,
        workspace_snapshot_id=context.workspace_snapshot_id,
    )


def resolve_target(request: TargetRequest, context: TargetResolutionContext) -> TargetResolutionResult:
    diagnostics: list[TargetResolutionDiagnostic] = []

    path_result = _explicit_path_result(request, context)
    if path_result is not None and path_result.resolution_status == "resolved":
        return path_result

    if path_result is not None and path_result.resolution_status == "unresolved":
        diagnostics.extend(path_result.diagnostics)
        explicit_path_fallback = request.constraints.get("allow_explicit_path_fallback")
        allow_path_fallback = explicit_path_fallback is True
        if context.policy.unresolved_explicit_target_blocks_fallback or not allow_path_fallback:
            return TargetResolutionResult(
                resolution_contract_version=RESOLUTION_CONTRACT_VERSION,
                resolution_status="unresolved",
                resolved_kind=None,
                resolved_target=None,
                resolved_path=None,
                resolved_symbol=None,
                resolution_source="explicit_path",
                resolution_strategy="exact",
                candidates=tuple(),
                evidence_anchors=tuple(),
                diagnostics=tuple(diagnostics),
                ambiguity_top_k=tuple(),
                transition_meta={},
                run_id=context.run_id,
                trace_id=context.trace_id,
                workspace_snapshot_id=context.workspace_snapshot_id,
            )

    if request.from_run:
        from_run_result = resolve_from_run_reference(request, context)
        if from_run_result.resolution_status in ("resolved", "blocked"):
            return from_run_result
        diagnostics.extend(from_run_result.diagnostics)

    symbol_candidates = _symbol_candidates(request, context)
    if len(symbol_candidates) == 1:
        return _resolved_result_from_candidate(
            symbol_candidates[0],
            request,
            context,
            resolution_source="symbol_match",
            resolution_strategy="exact",
            candidates=symbol_candidates,
            diagnostics=tuple(diagnostics),
        )
    if len(symbol_candidates) > 1:
        top_k = tuple(symbol_candidates[: context.policy.ambiguity_top_k])
        return TargetResolutionResult(
            resolution_contract_version=RESOLUTION_CONTRACT_VERSION,
            resolution_status="ambiguous",
            resolved_kind=None,
            resolved_target=None,
            resolved_path=None,
            resolved_symbol=None,
            resolution_source="symbol_match",
            resolution_strategy="best_effort_heuristic",
            candidates=tuple(symbol_candidates),
            evidence_anchors=tuple(),
            diagnostics=tuple(diagnostics)
            + (
                TargetResolutionDiagnostic(
                    code="ambiguous_target",
                    message=f"Target '{request.raw_target}' resolved to multiple symbol candidates.",
                    severity="warning",
                    context={"candidate_count": len(symbol_candidates), "top_k": context.policy.ambiguity_top_k},
                ),
            ),
            ambiguity_top_k=top_k,
            transition_meta={},
            run_id=context.run_id,
            trace_id=context.trace_id,
            workspace_snapshot_id=context.workspace_snapshot_id,
        )

    fallback_candidates = _fallback_candidates(request, context)
    if fallback_candidates:
        return _resolved_result_from_candidate(
            fallback_candidates[0],
            request,
            context,
            resolution_source="fallback",
            resolution_strategy="policy_fallback",
            candidates=fallback_candidates,
            diagnostics=tuple(diagnostics)
            + (
                TargetResolutionDiagnostic(
                    code="fallback_resolution_applied",
                    message="Target resolved via policy fallback.",
                    severity="info",
                    context={"fallback_kind": fallback_candidates[0].kind},
                ),
            ),
        )

    diagnostics.append(
        TargetResolutionDiagnostic(
            code="unresolved_symbol",
            message=f"Target '{request.raw_target}' could not be resolved.",
            severity="warning",
        )
    )
    return TargetResolutionResult(
        resolution_contract_version=RESOLUTION_CONTRACT_VERSION,
        resolution_status="unresolved",
        resolved_kind=None,
        resolved_target=None,
        resolved_path=None,
        resolved_symbol=None,
        resolution_source="symbol_match",
        resolution_strategy="best_effort_heuristic",
        candidates=tuple(),
        evidence_anchors=tuple(),
        diagnostics=tuple(diagnostics),
        ambiguity_top_k=tuple(),
        transition_meta={},
        run_id=context.run_id,
        trace_id=context.trace_id,
        workspace_snapshot_id=context.workspace_snapshot_id,
    )


__all__ = [
    "FromRunReference",
    "ResolutionPolicy",
    "RESOLUTION_CONTRACT_VERSION",
    "TargetCandidate",
    "TargetRequest",
    "TargetResolutionContext",
    "TargetResolutionDiagnostic",
    "TargetResolutionResult",
    "TransitionDecision",
    "order_target_candidates_for_resolution",
    "resolve_from_run_reference",
    "resolve_target",
    "validate_transition",
]

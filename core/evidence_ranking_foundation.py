"""Evidence Ranking Foundation (08): deterministic, explainable candidate ranking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, Sequence

from core.retrieval_foundation import RetrievalCandidate, RetrievalEvidence, RetrievalOutcome

RankingStatus = Literal["ok", "partial", "error"]
DiagnosticSeverity = Literal["info", "warning", "error"]
CandidateStatus = Literal["ok", "partial", "error"]

RANKING_POLICY_ID_DEFAULT = "ranking.default"
RANKING_POLICY_VERSION_DEFAULT = "08.1"

COMPONENT_RETRIEVAL_RAW_SCORE = "retrieval_raw_score"
COMPONENT_EVIDENCE_COUNT = "evidence_count"
COMPONENT_TERM_COVERAGE = "term_coverage"
COMPONENT_SOURCE_DETERMINISM = "source_determinism"
COMPONENT_RERANK_LOCATOR_TERM_MATCH = "rerank_locator_term_match"

DEFAULT_COMPONENT_WEIGHTS: tuple[tuple[str, float], ...] = (
    (COMPONENT_RETRIEVAL_RAW_SCORE, 0.45),
    (COMPONENT_EVIDENCE_COUNT, 0.20),
    (COMPONENT_TERM_COVERAGE, 0.25),
    (COMPONENT_SOURCE_DETERMINISM, 0.10),
    (COMPONENT_RERANK_LOCATOR_TERM_MATCH, 0.15),
)

DETERMINISTIC_SOURCE_TYPES: tuple[str, ...] = ("repo", "framework")


@dataclass(frozen=True)
class ScoreComponent:
    component_id: str
    weight: float
    raw_value: float
    contribution: float
    reason: str
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RankingDiagnostic:
    code: str
    message: str
    severity: DiagnosticSeverity
    candidate_locator: str | None = None
    context: Mapping[str, object] | None = None


@dataclass(frozen=True)
class RankingPolicy:
    policy_id: str
    policy_version: str
    component_weights: Mapping[str, float]
    tie_break_rules: tuple[str, ...]
    rerank_enabled: bool

    def __post_init__(self) -> None:
        if not self.policy_id:
            raise ValueError("policy_id is required.")
        if not self.policy_version:
            raise ValueError("policy_version is required.")
        required_core = {
            COMPONENT_RETRIEVAL_RAW_SCORE,
            COMPONENT_EVIDENCE_COUNT,
            COMPONENT_TERM_COVERAGE,
            COMPONENT_SOURCE_DETERMINISM,
        }
        required = set(required_core)
        if self.rerank_enabled:
            required.add(COMPONENT_RERANK_LOCATOR_TERM_MATCH)
        missing = sorted(required - set(self.component_weights.keys()))
        if missing:
            raise ValueError(f"Missing component weights: {', '.join(missing)}.")


@dataclass(frozen=True)
class RankingRequest:
    query_terms: tuple[str, ...]
    top_k: int | None = None
    enable_rerank: bool = False


@dataclass(frozen=True)
class RankingContext:
    policy: RankingPolicy
    run_id: str | None = None
    trace_id: str | None = None
    workspace_snapshot_id: str | None = None


@dataclass(frozen=True)
class TieBreakDecision:
    locator: str
    rules_applied: tuple[str, ...]
    tie_break_key: tuple[object, ...]
    tie_group_size: int = 2
    tie_group_rank: int | None = None


@dataclass(frozen=True)
class RankedCandidate:
    # Minimal local status semantics in Foundation 08:
    # - ok: score computed and candidate has evidence
    # - partial: score computed but candidate has no evidence
    # - error: score computation failed (not expected in current deterministic path)
    locator: str
    locator_kind: str
    evidence: tuple[RetrievalEvidence, ...]
    # Aggregated ranking value derived from weighted components.
    # Not a truth value and not guaranteed to be normalized to [0,1].
    score_total: float
    score_components: tuple[ScoreComponent, ...]
    policy_id: str
    status: CandidateStatus
    explanation: tuple[str, ...]
    tie_break_rules_applied: tuple[str, ...] = tuple()

    @property
    def ranking_policy_id(self) -> str:
        # Transitional alias for callers already using the previous field name.
        return self.policy_id


@dataclass(frozen=True)
class RankingOutcome:
    candidates: tuple[RankedCandidate, ...]
    policy_id: str
    policy_version: str
    diagnostics: tuple[RankingDiagnostic, ...]
    tie_break_decisions: tuple[TieBreakDecision, ...]
    status: RankingStatus
    run_id: str | None = None
    trace_id: str | None = None
    workspace_snapshot_id: str | None = None

    @property
    def ranked_candidates(self) -> tuple[RankedCandidate, ...]:
        # Transitional alias for previous naming.
        return self.candidates

    @property
    def ranking_policy_id(self) -> str:
        # Transitional alias for previous naming.
        return self.policy_id

    @property
    def ranking_policy_version(self) -> str:
        # Transitional alias for previous naming.
        return self.policy_version


def default_ranking_policy() -> RankingPolicy:
    return RankingPolicy(
        policy_id=RANKING_POLICY_ID_DEFAULT,
        policy_version=RANKING_POLICY_VERSION_DEFAULT,
        component_weights=dict(DEFAULT_COMPONENT_WEIGHTS),
        tie_break_rules=("score_total", "term_coverage", "evidence_count", "locator_lexical"),
        rerank_enabled=False,
    )


def rerank_ranking_policy() -> RankingPolicy:
    return RankingPolicy(
        policy_id=f"{RANKING_POLICY_ID_DEFAULT}.rerank",
        policy_version=RANKING_POLICY_VERSION_DEFAULT,
        component_weights=dict(DEFAULT_COMPONENT_WEIGHTS),
        tie_break_rules=("score_total", "term_coverage", "evidence_count", "locator_lexical"),
        rerank_enabled=True,
    )


def _normalize_terms(request: RankingRequest) -> tuple[str, ...]:
    return tuple(sorted({term.strip().lower() for term in request.query_terms if term.strip()}))


def _evidence_by_locator(retrieval_outcome: RetrievalOutcome) -> Mapping[str, tuple[RetrievalEvidence, ...]]:
    grouped: dict[str, list[RetrievalEvidence]] = {}
    for evidence in retrieval_outcome.evidence_items:
        grouped.setdefault(evidence.locator, []).append(evidence)
    return {
        locator: tuple(
            sorted(
                items,
                key=lambda item: (
                    item.locator,
                    -1 if item.line is None else item.line,
                    item.term.lower(),
                    item.source_type,
                    item.source_origin,
                    item.retrieval_source,
                    item.text,
                ),
            )
        )
        for locator, items in grouped.items()
    }


def _source_determinism_ratio(candidate: RetrievalCandidate) -> float:
    source_types = candidate.merged_source_types or (candidate.source_type,)
    deterministic = sum(1 for item in source_types if item in DETERMINISTIC_SOURCE_TYPES)
    return float(deterministic) / float(len(source_types))


def _term_coverage(
    candidate: RetrievalCandidate,
    evidence_items: Sequence[RetrievalEvidence],
    normalized_terms: Sequence[str],
) -> float:
    if not normalized_terms:
        return 0.0
    matched_terms: set[str] = set()
    signal_terms = {
        signal.split(":", 1)[1].lower()
        for signal in candidate.retrieval_signals
        if ":" in signal and signal.split(":", 1)[1]
    }
    for term in normalized_terms:
        if term in signal_terms:
            matched_terms.add(term)
    for evidence in evidence_items:
        term = evidence.term.lower()
        if term in normalized_terms:
            matched_terms.add(term)
    return float(len(matched_terms)) / float(len(normalized_terms))


def _component(
    component_id: str,
    weight: float,
    raw_value: float,
    reason: str,
    metadata: Mapping[str, object] | None = None,
) -> ScoreComponent:
    contribution = round(raw_value * weight, 6)
    return ScoreComponent(
        component_id=component_id,
        weight=weight,
        raw_value=round(raw_value, 6),
        contribution=contribution,
        reason=reason,
        metadata=metadata or {},
    )


def _compute_score_components(
    request: RankingRequest,
    candidate: RetrievalCandidate,
    evidence_items: Sequence[RetrievalEvidence],
    policy: RankingPolicy,
    normalized_terms: Sequence[str],
) -> tuple[ScoreComponent, ...]:
    retrieval_raw_score = float(candidate.raw_retrieval_score or 0.0)
    evidence_count_value = min(float(len(evidence_items)), 10.0) / 10.0
    term_coverage = _term_coverage(candidate, evidence_items, normalized_terms)
    source_determinism = _source_determinism_ratio(candidate)

    components: list[ScoreComponent] = [
        _component(
            COMPONENT_RETRIEVAL_RAW_SCORE,
            policy.component_weights[COMPONENT_RETRIEVAL_RAW_SCORE],
            retrieval_raw_score,
            "Source-native retrieval score.",
        ),
        _component(
            COMPONENT_EVIDENCE_COUNT,
            policy.component_weights[COMPONENT_EVIDENCE_COUNT],
            evidence_count_value,
            "Evidence quantity normalized to stable cap.",
            metadata={"evidence_count": len(evidence_items)},
        ),
        _component(
            COMPONENT_TERM_COVERAGE,
            policy.component_weights[COMPONENT_TERM_COVERAGE],
            term_coverage,
            "Coverage of request terms in candidate signals/evidence.",
            metadata={"query_term_count": len(normalized_terms)},
        ),
        _component(
            COMPONENT_SOURCE_DETERMINISM,
            policy.component_weights[COMPONENT_SOURCE_DETERMINISM],
            source_determinism,
            "Fraction of deterministic source types (repo/framework).",
        ),
    ]

    if request.enable_rerank and policy.rerank_enabled:
        locator_lower = candidate.locator.lower()
        locator_term_match = 1.0 if any(term in locator_lower for term in normalized_terms) else 0.0
        components.append(
            _component(
                COMPONENT_RERANK_LOCATOR_TERM_MATCH,
                policy.component_weights[COMPONENT_RERANK_LOCATOR_TERM_MATCH],
                locator_term_match,
                "Declared rerank step: locator-term match signal.",
            )
        )
    return tuple(components)


def _aggregate_score(components: Sequence[ScoreComponent]) -> float:
    return round(sum(component.contribution for component in components), 6)


def _build_explanation(components: Sequence[ScoreComponent], tie_break_rules: Sequence[str]) -> tuple[str, ...]:
    lines = [f"{component.component_id}={component.contribution:.6f}" for component in components]
    if tie_break_rules:
        lines.append(f"tie_break={','.join(tie_break_rules)}")
    return tuple(lines)


def _term_coverage_component_value(components: Sequence[ScoreComponent]) -> float:
    for component in components:
        if component.component_id == COMPONENT_TERM_COVERAGE:
            return component.raw_value
    return 0.0


def _evidence_count_component_value(components: Sequence[ScoreComponent]) -> float:
    for component in components:
        if component.component_id == COMPONENT_EVIDENCE_COUNT:
            return component.raw_value
    return 0.0


def _tie_break_key(candidate: RankedCandidate) -> tuple[object, ...]:
    return (
        -candidate.score_total,
        -_term_coverage_component_value(candidate.score_components),
        -_evidence_count_component_value(candidate.score_components),
        candidate.locator,
    )


def _apply_tie_break(
    ranked_candidates: Sequence[RankedCandidate],
    policy: RankingPolicy,
) -> tuple[tuple[RankedCandidate, ...], tuple[TieBreakDecision, ...]]:
    sorted_candidates = sorted(ranked_candidates, key=_tie_break_key)
    tie_break_decisions: list[TieBreakDecision] = []
    score_groups: dict[float, list[RankedCandidate]] = {}
    for candidate in sorted_candidates:
        score_groups.setdefault(candidate.score_total, []).append(candidate)
    score_group_rank_seen: dict[float, int] = {score: 0 for score in score_groups.keys()}

    result: list[RankedCandidate] = []
    for index, candidate in enumerate(sorted_candidates):
        tie_rules: tuple[str, ...] = tuple()
        if index > 0 and abs(candidate.score_total - sorted_candidates[index - 1].score_total) < 1e-9:
            tie_rules = policy.tie_break_rules
            group = score_groups.get(candidate.score_total, [candidate])
            score_group_rank_seen[candidate.score_total] += 1
            tie_break_decisions.append(
                TieBreakDecision(
                    locator=candidate.locator,
                    rules_applied=tie_rules,
                    tie_break_key=_tie_break_key(candidate),
                    tie_group_size=len(group),
                    tie_group_rank=score_group_rank_seen[candidate.score_total],
                )
            )
        result.append(
            RankedCandidate(
                locator=candidate.locator,
                locator_kind=candidate.locator_kind,
                evidence=candidate.evidence,
                score_total=candidate.score_total,
                score_components=candidate.score_components,
                policy_id=candidate.policy_id,
                status=candidate.status,
                explanation=_build_explanation(candidate.score_components, tie_rules),
                tie_break_rules_applied=tie_rules,
            )
        )
    return tuple(result), tuple(tie_break_decisions)


def _apply_optional_rerank_diagnostics(
    request: RankingRequest,
    policy: RankingPolicy,
    ranked_candidates: Sequence[RankedCandidate],
) -> tuple[RankingDiagnostic, ...]:
    if not request.enable_rerank:
        return tuple()
    if not policy.rerank_enabled:
        return (
            RankingDiagnostic(
                code="rerank_disabled_by_policy",
                message="Rerank requested but disabled by policy.",
                severity="warning",
            ),
        )
    return (
        RankingDiagnostic(
            code="rerank_applied",
            message="Declared rerank step applied via explicit score component.",
            severity="info",
            context={"candidate_count": len(ranked_candidates), "component_id": COMPONENT_RERANK_LOCATOR_TERM_MATCH},
        ),
    )


def _candidate_status(evidence: Sequence[RetrievalEvidence], components: Sequence[ScoreComponent]) -> CandidateStatus:
    if not components:
        return "error"
    return "ok" if evidence else "partial"


def _derive_outcome_status(
    retrieval_outcome: RetrievalOutcome,
    candidates: Sequence[RankedCandidate],
    diagnostics: Sequence[RankingDiagnostic],
) -> RankingStatus:
    # Foundation 08 status priority:
    # error > partial > ok
    # (blocked retrieval is represented as partial in Foundation 08 status space).
    has_error_diagnostic = any(diagnostic.severity == "error" for diagnostic in diagnostics)
    has_error_candidate = any(candidate.status == "error" for candidate in candidates)
    if retrieval_outcome.status == "error" or has_error_diagnostic or has_error_candidate:
        return "error"
    if not candidates:
        return "partial" if diagnostics or retrieval_outcome.status in ("partial", "blocked") else "error"
    if retrieval_outcome.status in ("partial", "blocked"):
        return "partial"
    if any(candidate.status == "partial" for candidate in candidates):
        return "partial"
    return "ok"


def rank_evidence(request: RankingRequest, retrieval_outcome: RetrievalOutcome, context: RankingContext) -> RankingOutcome:
    diagnostics: list[RankingDiagnostic] = []
    policy = context.policy
    normalized_terms = _normalize_terms(request)

    if retrieval_outcome.status == "error":
        diagnostics.append(
            RankingDiagnostic(
                code="retrieval_error",
                message="Cannot rank evidence because retrieval outcome is error.",
                severity="error",
            )
        )
        return RankingOutcome(
            candidates=tuple(),
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            diagnostics=tuple(diagnostics),
            tie_break_decisions=tuple(),
            status="error",
            run_id=context.run_id,
            trace_id=context.trace_id,
            workspace_snapshot_id=context.workspace_snapshot_id,
        )

    evidence_lookup = _evidence_by_locator(retrieval_outcome)
    ranked_candidates: list[RankedCandidate] = []
    for candidate in retrieval_outcome.candidates:
        evidence = evidence_lookup.get(candidate.locator, tuple())
        components = _compute_score_components(request, candidate, evidence, policy, normalized_terms)
        score_total = _aggregate_score(components)
        ranked_candidates.append(
            RankedCandidate(
                locator=candidate.locator,
                locator_kind=candidate.locator_kind,
                evidence=evidence,
                score_total=score_total,
                score_components=components,
                policy_id=policy.policy_id,
                status=_candidate_status(evidence, components),
                explanation=_build_explanation(components, tuple()),
            )
        )

    if not ranked_candidates:
        diagnostics.append(
            RankingDiagnostic(
                code="no_candidates_to_rank",
                message="No retrieval candidates available for ranking.",
                severity="warning",
            )
        )

    sorted_candidates, tie_break_decisions = _apply_tie_break(ranked_candidates, policy)
    diagnostics.extend(_apply_optional_rerank_diagnostics(request, policy, sorted_candidates))

    limited_candidates = sorted_candidates
    if request.top_k is not None and request.top_k >= 0:
        if request.top_k < len(sorted_candidates):
            diagnostics.append(
                RankingDiagnostic(
                    code="ranking_top_k_applied",
                    message=f"Ranking result truncated by top_k ({len(sorted_candidates)} -> {request.top_k}).",
                    severity="info",
                    context={"before": len(sorted_candidates), "after": request.top_k},
                )
            )
        limited_candidates = sorted_candidates[: request.top_k]

    status = _derive_outcome_status(retrieval_outcome, limited_candidates, diagnostics)

    return RankingOutcome(
        candidates=tuple(limited_candidates),
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        diagnostics=tuple(diagnostics),
        tie_break_decisions=tie_break_decisions,
        status=status,
        run_id=context.run_id,
        trace_id=context.trace_id,
        workspace_snapshot_id=context.workspace_snapshot_id,
    )


__all__ = [
    "DETERMINISTIC_SOURCE_TYPES",
    "RANKING_POLICY_ID_DEFAULT",
    "RANKING_POLICY_VERSION_DEFAULT",
    "RankedCandidate",
    "RankingContext",
    "RankingDiagnostic",
    "RankingOutcome",
    "RankingPolicy",
    "RankingRequest",
    "ScoreComponent",
    "TieBreakDecision",
    "default_ranking_policy",
    "rerank_ranking_policy",
    "rank_evidence",
]

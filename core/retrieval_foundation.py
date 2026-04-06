"""Retrieval Foundation (07): deterministic candidate/evidence retrieval contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Callable, Literal, Mapping, Sequence

RETRIEVAL_CONTRACT_VERSION = "07.1"

RetrievalStatus = Literal["ok", "partial", "blocked", "error"]
DiagnosticSeverity = Literal["info", "warning", "error"]
SourceType = Literal["repo", "framework", "web_docs", "web_general", "external"]
TargetScope = Literal["code", "docs", "general"]
SourceScope = Literal["repo_only", "framework_only", "web_only", "all", "mixed_policy"]
LocatorKind = Literal["path", "url"]
SelectionStatus = Literal[
    "selected",
    "blocked_policy",
    "blocked_budget",
    "blocked_nondeterministic",
    "out_of_scope",
    "out_of_target",
]

ALLOWED_SIGNAL_TYPES: tuple[str, ...] = ("symbol", "keyword", "path", "semantic", "hint")


@dataclass(frozen=True)
class RetrievalDiagnostic:
    code: str
    message: str
    severity: DiagnosticSeverity
    source_type: SourceType | None = None
    source_origin: str | None = None
    retrieval_source: str | None = None
    context: Mapping[str, object] | None = None


@dataclass(frozen=True)
class QueryTermSignal:
    term: str
    signal_type: str
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.term.strip():
            raise ValueError("query term must not be empty.")
        if self.signal_type not in ALLOWED_SIGNAL_TYPES:
            raise ValueError(
                f"signal_type '{self.signal_type}' is invalid. "
                f"Allowed: {', '.join(ALLOWED_SIGNAL_TYPES)}."
            )


@dataclass(frozen=True)
class BudgetView:
    max_candidates: int = 50
    max_evidence_items: int = 200
    max_external_calls: int = 0

    def __post_init__(self) -> None:
        if self.max_candidates < 0:
            raise ValueError("max_candidates must be >= 0.")
        if self.max_evidence_items < 0:
            raise ValueError("max_evidence_items must be >= 0.")
        if self.max_external_calls < 0:
            raise ValueError("max_external_calls must be >= 0.")


@dataclass(frozen=True)
class PolicyContext:
    allowed_source_types: tuple[SourceType, ...] = ("repo", "framework", "web_docs", "web_general", "external")
    allow_nondeterministic_sources: bool = False


@dataclass(frozen=True)
class RetrievalRequest:
    query_terms: tuple[QueryTermSignal, ...]
    target_scope: TargetScope
    source_scope: SourceScope
    budget_view: BudgetView
    policy_context: PolicyContext


@dataclass(frozen=True)
class SourceDocument:
    path_or_url: str
    text: str
    line_hints: Mapping[str, int] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalSourceAdapter:
    source_type: SourceType
    source_origin: str
    retrieval_source: str
    nondeterministic: bool
    target_scopes: tuple[TargetScope, ...]
    documents: tuple[SourceDocument, ...]


@dataclass(frozen=True)
class RetrievalContext:
    sources: tuple[RetrievalSourceAdapter, ...]
    workspace_snapshot_id: str | None = None
    run_id: str | None = None
    trace_id: str | None = None
    # Extension point for Foundation 12 locator normalization integration.
    locator_normalizer: Callable[[str], tuple[str, LocatorKind]] | None = None


@dataclass(frozen=True)
class RetrievalCandidate:
    path_or_url: str
    locator: str
    locator_kind: LocatorKind
    source_type: SourceType
    source_origin: str
    retrieval_source: str
    retrieval_signals: tuple[str, ...]
    raw_retrieval_score: float | None = None
    merged_source_types: tuple[SourceType, ...] = tuple()
    merged_source_origins: tuple[str, ...] = tuple()
    merged_retrieval_sources: tuple[str, ...] = tuple()


@dataclass(frozen=True)
class RetrievalEvidence:
    path_or_url: str
    locator: str
    locator_kind: LocatorKind
    line: int | None
    text: str
    term: str
    retrieval_source: str
    source_type: SourceType
    source_origin: str
    retrieval_signals: tuple[str, ...]
    merged_source_types: tuple[SourceType, ...] = tuple()
    merged_source_origins: tuple[str, ...] = tuple()
    merged_retrieval_sources: tuple[str, ...] = tuple()


@dataclass(frozen=True)
class RetrievalSourceUsage:
    source_type: SourceType
    source_origin: str
    retrieval_source: str
    attempted: bool
    used: bool
    candidate_count: int
    evidence_count: int
    nondeterministic: bool
    selection_status: SelectionStatus


@dataclass(frozen=True)
class RetrievalOutcome:
    retrieval_contract_version: str
    candidates: tuple[RetrievalCandidate, ...]
    evidence_items: tuple[RetrievalEvidence, ...]
    retrieval_diagnostics: tuple[RetrievalDiagnostic, ...]
    source_usage: tuple[RetrievalSourceUsage, ...]
    status: RetrievalStatus
    workspace_snapshot_id: str | None = None
    run_id: str | None = None
    trace_id: str | None = None


def _is_url(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _normalize_locator(path_or_url: str) -> tuple[str, LocatorKind]:
    locator_kind: LocatorKind = "url" if _is_url(path_or_url) else "path"
    return path_or_url.strip(), locator_kind


def _resolve_locator(path_or_url: str, context: RetrievalContext) -> tuple[str, LocatorKind]:
    if context.locator_normalizer is not None:
        return context.locator_normalizer(path_or_url)
    return _normalize_locator(path_or_url)


def _source_scope_allows(source_scope: SourceScope, source_type: SourceType) -> bool:
    if source_scope == "all":
        return True
    if source_scope == "repo_only":
        return source_type == "repo"
    if source_scope == "framework_only":
        return source_type == "framework"
    if source_scope == "web_only":
        return source_type in ("web_docs", "web_general")
    if source_scope == "mixed_policy":
        return source_type in ("repo", "framework", "web_docs")
    return False


def _is_external_source(source_type: SourceType) -> bool:
    return source_type in ("web_docs", "web_general", "external")


def _select_sources(
    request: RetrievalRequest,
    context: RetrievalContext,
) -> tuple[
    tuple[RetrievalSourceAdapter, ...],
    tuple[RetrievalSourceUsage, ...],
    list[RetrievalDiagnostic],
    bool,
]:
    diagnostics: list[RetrievalDiagnostic] = []
    selected: list[RetrievalSourceAdapter] = []
    usage: list[RetrievalSourceUsage] = []
    partial = False
    external_calls_used = 0

    sorted_sources = sorted(
        context.sources,
        key=lambda item: (item.source_type, item.source_origin, item.retrieval_source),
    )
    for source in sorted_sources:
        selection_status: SelectionStatus | None = None
        if request.target_scope not in source.target_scopes:
            selection_status = "out_of_target"
            usage.append(
                RetrievalSourceUsage(
                    source_type=source.source_type,
                    source_origin=source.source_origin,
                    retrieval_source=source.retrieval_source,
                    attempted=False,
                    used=False,
                    candidate_count=0,
                    evidence_count=0,
                    nondeterministic=source.nondeterministic,
                    selection_status=selection_status,
                )
            )
            continue
        if not _source_scope_allows(request.source_scope, source.source_type):
            selection_status = "out_of_scope"
            usage.append(
                RetrievalSourceUsage(
                    source_type=source.source_type,
                    source_origin=source.source_origin,
                    retrieval_source=source.retrieval_source,
                    attempted=False,
                    used=False,
                    candidate_count=0,
                    evidence_count=0,
                    nondeterministic=source.nondeterministic,
                    selection_status=selection_status,
                )
            )
            continue
        if source.source_type not in request.policy_context.allowed_source_types:
            diagnostics.append(
                RetrievalDiagnostic(
                    code="source_blocked_by_policy",
                    message=f"Source '{source.source_origin}' blocked by policy.",
                    severity="warning",
                    source_type=source.source_type,
                    source_origin=source.source_origin,
                    retrieval_source=source.retrieval_source,
                    context={
                        "selection_status": "blocked_policy",
                        "source_scope": request.source_scope,
                        "target_scope": request.target_scope,
                    },
                )
            )
            partial = True
            selection_status = "blocked_policy"
            usage.append(
                RetrievalSourceUsage(
                    source_type=source.source_type,
                    source_origin=source.source_origin,
                    retrieval_source=source.retrieval_source,
                    attempted=False,
                    used=False,
                    candidate_count=0,
                    evidence_count=0,
                    nondeterministic=source.nondeterministic,
                    selection_status=selection_status,
                )
            )
            continue
        if source.nondeterministic and not request.policy_context.allow_nondeterministic_sources:
            diagnostics.append(
                RetrievalDiagnostic(
                    code="nondeterministic_source_blocked",
                    message=f"Nondeterministic source '{source.source_origin}' blocked by policy.",
                    severity="warning",
                    source_type=source.source_type,
                    source_origin=source.source_origin,
                    retrieval_source=source.retrieval_source,
                    context={
                        "selection_status": "blocked_nondeterministic",
                        "allow_nondeterministic_sources": request.policy_context.allow_nondeterministic_sources,
                    },
                )
            )
            partial = True
            selection_status = "blocked_nondeterministic"
            usage.append(
                RetrievalSourceUsage(
                    source_type=source.source_type,
                    source_origin=source.source_origin,
                    retrieval_source=source.retrieval_source,
                    attempted=False,
                    used=False,
                    candidate_count=0,
                    evidence_count=0,
                    nondeterministic=source.nondeterministic,
                    selection_status=selection_status,
                )
            )
            continue
        if _is_external_source(source.source_type):
            if external_calls_used >= request.budget_view.max_external_calls:
                diagnostics.append(
                    RetrievalDiagnostic(
                        code="external_call_budget_exhausted",
                        message=f"External source '{source.source_origin}' skipped due to budget.",
                        severity="warning",
                        source_type=source.source_type,
                        source_origin=source.source_origin,
                        retrieval_source=source.retrieval_source,
                        context={
                            "selection_status": "blocked_budget",
                            "max_external_calls": request.budget_view.max_external_calls,
                            "external_calls_used": external_calls_used,
                        },
                    )
                )
                partial = True
                selection_status = "blocked_budget"
                usage.append(
                    RetrievalSourceUsage(
                        source_type=source.source_type,
                        source_origin=source.source_origin,
                        retrieval_source=source.retrieval_source,
                        attempted=False,
                        used=False,
                        candidate_count=0,
                        evidence_count=0,
                        nondeterministic=source.nondeterministic,
                        selection_status=selection_status,
                    )
                )
                continue
            external_calls_used += 1

        selected.append(source)
        usage.append(
            RetrievalSourceUsage(
                source_type=source.source_type,
                source_origin=source.source_origin,
                retrieval_source=source.retrieval_source,
                attempted=True,
                used=False,
                candidate_count=0,
                evidence_count=0,
                nondeterministic=source.nondeterministic,
                selection_status="selected",
            )
        )
        if source.nondeterministic:
            diagnostics.append(
                RetrievalDiagnostic(
                    code="nondeterministic_source_used",
                    message=f"Source '{source.source_origin}' is nondeterministic.",
                    severity="info",
                    source_type=source.source_type,
                    source_origin=source.source_origin,
                    retrieval_source=source.retrieval_source,
                    context={"selection_status": "selected"},
                )
            )

    return tuple(selected), tuple(usage), diagnostics, partial


def _build_candidate(
    document: SourceDocument,
    source: RetrievalSourceAdapter,
    term_matches: tuple[QueryTermSignal, ...],
    context: RetrievalContext,
) -> RetrievalCandidate:
    locator, locator_kind = _resolve_locator(document.path_or_url, context)
    raw_score = sum(term.weight for term in term_matches)
    signals = tuple(sorted({f"{term.signal_type}:{term.term}" for term in term_matches}))
    return RetrievalCandidate(
        path_or_url=document.path_or_url,
        locator=locator,
        locator_kind=locator_kind,
        source_type=source.source_type,
        source_origin=source.source_origin,
        retrieval_source=source.retrieval_source,
        retrieval_signals=signals,
        raw_retrieval_score=float(raw_score),
        merged_source_types=(source.source_type,),
        merged_source_origins=(source.source_origin,),
        merged_retrieval_sources=(source.retrieval_source,),
    )


def _build_evidence_items(
    document: SourceDocument,
    source: RetrievalSourceAdapter,
    term_matches: tuple[QueryTermSignal, ...],
    context: RetrievalContext,
) -> tuple[RetrievalEvidence, ...]:
    locator, locator_kind = _resolve_locator(document.path_or_url, context)
    items: list[RetrievalEvidence] = []
    for term_signal in term_matches:
        line = document.line_hints.get(term_signal.term)
        snippet = _build_evidence_snippet(document.text, term_signal.term, line)
        items.append(
            RetrievalEvidence(
                path_or_url=document.path_or_url,
                locator=locator,
                locator_kind=locator_kind,
                line=line,
                text=snippet,
                term=term_signal.term,
                retrieval_source=source.retrieval_source,
                source_type=source.source_type,
                source_origin=source.source_origin,
                retrieval_signals=(f"{term_signal.signal_type}:{term_signal.term}",),
                merged_source_types=(source.source_type,),
                merged_source_origins=(source.source_origin,),
                merged_retrieval_sources=(source.retrieval_source,),
            )
        )
    return tuple(items)


def _build_evidence_snippet(text: str, term: str, line: int | None) -> str:
    max_chars = 240
    normalized = text.strip()
    if not normalized:
        return normalized

    lines = normalized.splitlines()
    if line is not None and line >= 1 and line <= len(lines):
        start = max(0, line - 2)
        end = min(len(lines), line + 1)
        snippet = "\n".join(lines[start:end]).strip()
        if len(snippet) > max_chars:
            snippet = snippet[:max_chars].rstrip()
        return snippet

    lowered_text = normalized.lower()
    lowered_term = term.lower()
    idx = lowered_text.find(lowered_term)
    if idx >= 0:
        left = max(0, idx - 80)
        right = min(len(normalized), idx + len(term) + 80)
        snippet = normalized[left:right].strip()
        if len(snippet) > max_chars:
            snippet = snippet[:max_chars].rstrip()
        return snippet

    return normalized[:max_chars].rstrip()


def _generate_candidates_and_evidence(
    request: RetrievalRequest,
    selected_sources: Sequence[RetrievalSourceAdapter],
    context: RetrievalContext,
    source_usage_seed: Sequence[RetrievalSourceUsage],
) -> tuple[list[RetrievalCandidate], list[RetrievalEvidence], tuple[RetrievalSourceUsage, ...]]:
    candidates: list[RetrievalCandidate] = []
    evidence_items: list[RetrievalEvidence] = []
    usage_by_key = {
        (item.source_type, item.source_origin, item.retrieval_source): item for item in source_usage_seed
    }
    lower_terms = tuple(term.term.lower() for term in request.query_terms)

    for source in selected_sources:
        source_candidates = 0
        source_evidence = 0
        for document in source.documents:
            doc_text = document.text.lower()
            doc_locator = document.path_or_url.lower()
            matched: list[QueryTermSignal] = []
            for idx, term in enumerate(lower_terms):
                if term in doc_text or term in doc_locator:
                    matched.append(request.query_terms[idx])
            if not matched:
                continue
            term_matches = tuple(matched)
            candidate = _build_candidate(document, source, term_matches, context)
            candidates.append(candidate)
            source_candidates += 1
            evidence_for_doc = _build_evidence_items(document, source, term_matches, context)
            evidence_items.extend(evidence_for_doc)
            source_evidence += len(evidence_for_doc)

        key = (source.source_type, source.source_origin, source.retrieval_source)
        previous = usage_by_key[key]
        usage_by_key[key] = RetrievalSourceUsage(
            source_type=previous.source_type,
            source_origin=previous.source_origin,
            retrieval_source=previous.retrieval_source,
            attempted=previous.attempted,
            used=source_candidates > 0 or source_evidence > 0,
            candidate_count=source_candidates,
            evidence_count=source_evidence,
            nondeterministic=previous.nondeterministic,
            selection_status=previous.selection_status,
        )

    candidates.sort(
        key=lambda item: (
            item.path_or_url,
            item.source_type,
            item.source_origin,
            item.retrieval_source,
            tuple(item.retrieval_signals),
        )
    )
    evidence_items.sort(
        key=lambda item: (
            item.path_or_url,
            -1 if item.line is None else item.line,
            item.term,
            item.source_type,
            item.source_origin,
            item.retrieval_source,
        )
    )
    usage = tuple(
        usage_by_key[key]
        for key in sorted(usage_by_key.keys(), key=lambda item: (item[0], item[1], item[2]))
    )
    return candidates, evidence_items, usage


def _dedupe_candidates(
    candidates: Sequence[RetrievalCandidate],
) -> tuple[tuple[RetrievalCandidate, ...], list[RetrievalDiagnostic]]:
    diagnostics: list[RetrievalDiagnostic] = []
    merged: dict[str, RetrievalCandidate] = {}
    grouped_sources: dict[str, set[SourceType]] = {}
    grouped_origins: dict[str, set[str]] = {}
    grouped_retrievers: dict[str, set[str]] = {}
    grouped_signals: dict[str, set[str]] = {}
    raw_scores: dict[str, float] = {}

    for candidate in candidates:
        key = candidate.locator
        grouped_sources.setdefault(key, set()).add(candidate.source_type)
        grouped_origins.setdefault(key, set()).add(candidate.source_origin)
        grouped_retrievers.setdefault(key, set()).add(candidate.retrieval_source)
        grouped_signals.setdefault(key, set()).update(candidate.retrieval_signals)
        raw_scores[key] = max(raw_scores.get(key, candidate.raw_retrieval_score or 0.0), candidate.raw_retrieval_score or 0.0)
        if key in merged:
            diagnostics.append(
                RetrievalDiagnostic(
                    code="candidate_deduplicated",
                    message=f"Candidate deduplicated for locator '{key}'.",
                    severity="info",
                    context={"dedupe_key": key, "kind": "candidate"},
                )
            )
            continue
        merged[key] = candidate

    result: list[RetrievalCandidate] = []
    for key in sorted(merged.keys()):
        base = merged[key]
        result.append(
            RetrievalCandidate(
                path_or_url=base.path_or_url,
                locator=base.locator,
                locator_kind=base.locator_kind,
                source_type=base.source_type,
                source_origin=base.source_origin,
                retrieval_source=base.retrieval_source,
                retrieval_signals=tuple(sorted(grouped_signals[key])),
                raw_retrieval_score=raw_scores[key],
                merged_source_types=tuple(sorted(grouped_sources[key])),
                merged_source_origins=tuple(sorted(grouped_origins[key])),
                merged_retrieval_sources=tuple(sorted(grouped_retrievers[key])),
            )
        )
    return tuple(result), diagnostics


def _evidence_dedupe_key(evidence: RetrievalEvidence) -> str:
    payload = f"{evidence.locator}|{evidence.line}|{evidence.term}|{evidence.text}"
    return sha256(payload.encode("utf-8")).hexdigest()


def _dedupe_evidence(
    evidence_items: Sequence[RetrievalEvidence],
) -> tuple[tuple[RetrievalEvidence, ...], list[RetrievalDiagnostic]]:
    diagnostics: list[RetrievalDiagnostic] = []
    merged: dict[str, RetrievalEvidence] = {}
    grouped_sources: dict[str, set[SourceType]] = {}
    grouped_origins: dict[str, set[str]] = {}
    grouped_retrievers: dict[str, set[str]] = {}
    grouped_signals: dict[str, set[str]] = {}

    for evidence in evidence_items:
        key = _evidence_dedupe_key(evidence)
        grouped_sources.setdefault(key, set()).add(evidence.source_type)
        grouped_origins.setdefault(key, set()).add(evidence.source_origin)
        grouped_retrievers.setdefault(key, set()).add(evidence.retrieval_source)
        grouped_signals.setdefault(key, set()).update(evidence.retrieval_signals)
        if key in merged:
            diagnostics.append(
                RetrievalDiagnostic(
                    code="evidence_deduplicated",
                    message=f"Evidence deduplicated for locator '{evidence.locator}'.",
                    severity="info",
                    context={"dedupe_key": key, "kind": "evidence", "locator": evidence.locator},
                )
            )
            continue
        merged[key] = evidence

    result: list[RetrievalEvidence] = []
    for key in sorted(merged.keys()):
        base = merged[key]
        result.append(
            RetrievalEvidence(
                path_or_url=base.path_or_url,
                locator=base.locator,
                locator_kind=base.locator_kind,
                line=base.line,
                text=base.text,
                term=base.term,
                retrieval_source=base.retrieval_source,
                source_type=base.source_type,
                source_origin=base.source_origin,
                retrieval_signals=tuple(sorted(grouped_signals[key])),
                merged_source_types=tuple(sorted(grouped_sources[key])),
                merged_source_origins=tuple(sorted(grouped_origins[key])),
                merged_retrieval_sources=tuple(sorted(grouped_retrievers[key])),
            )
        )
    result.sort(key=lambda item: (item.locator, -1 if item.line is None else item.line, item.term, item.text))
    return tuple(result), diagnostics


def _apply_budget_limits(
    request: RetrievalRequest,
    candidates: tuple[RetrievalCandidate, ...],
    evidence_items: tuple[RetrievalEvidence, ...],
) -> tuple[tuple[RetrievalCandidate, ...], tuple[RetrievalEvidence, ...], list[RetrievalDiagnostic], bool]:
    diagnostics: list[RetrievalDiagnostic] = []
    partial = False
    limited_candidates = candidates
    limited_evidence = evidence_items

    if len(limited_candidates) > request.budget_view.max_candidates:
        before = len(limited_candidates)
        limited_candidates = limited_candidates[: request.budget_view.max_candidates]
        diagnostics.append(
            RetrievalDiagnostic(
                code="candidate_budget_limited",
                message=f"Candidate list was truncated by budget ({before} -> {len(limited_candidates)}).",
                severity="warning",
                context={
                    "before": before,
                    "after": len(limited_candidates),
                    "max_candidates": request.budget_view.max_candidates,
                },
            )
        )
        partial = True

    # Keep candidate/evidence relationship consistent after candidate truncation.
    candidate_locators = {item.locator for item in limited_candidates}
    evidence_before_candidate_filter = len(limited_evidence)
    limited_evidence = tuple(item for item in limited_evidence if item.locator in candidate_locators)
    filtered_out = evidence_before_candidate_filter - len(limited_evidence)
    if filtered_out > 0:
        diagnostics.append(
            RetrievalDiagnostic(
                code="evidence_filtered_for_candidate_budget",
                message=(
                    "Evidence for candidates removed by budget truncation was filtered "
                    f"({filtered_out} item(s))."
                ),
                severity="info",
                context={
                    "filtered_out": filtered_out,
                    "remaining_evidence": len(limited_evidence),
                },
            )
        )

    if len(limited_evidence) > request.budget_view.max_evidence_items:
        before = len(limited_evidence)
        limited_evidence = limited_evidence[: request.budget_view.max_evidence_items]
        diagnostics.append(
            RetrievalDiagnostic(
                code="evidence_budget_limited",
                message=f"Evidence list was truncated by budget ({before} -> {len(limited_evidence)}).",
                severity="warning",
                context={
                    "before": before,
                    "after": len(limited_evidence),
                    "max_evidence_items": request.budget_view.max_evidence_items,
                },
            )
        )
        partial = True

    evidence_locators = {item.locator for item in limited_evidence}
    missing_candidate_evidence = sorted(candidate_locators - evidence_locators)
    if missing_candidate_evidence:
        diagnostics.append(
            RetrievalDiagnostic(
                code="candidates_without_evidence_after_budget",
                message=(
                    "Some remaining candidates have no remaining evidence after budget truncation "
                    f"({len(missing_candidate_evidence)} candidate(s))."
                ),
                severity="warning",
                context={
                    "missing_candidate_count": len(missing_candidate_evidence),
                    "missing_candidate_locators": tuple(missing_candidate_evidence[:3]),
                },
            )
        )

    if partial:
        diagnostics.append(
            RetrievalDiagnostic(
                code="budget_truncation_applied",
                message=(
                    "Budget truncation applied to retrieval results "
                    f"(candidates={len(candidates)}, evidence={len(evidence_items)})."
                ),
                severity="info",
                context={
                    "candidates_before": len(candidates),
                    "candidates_after": len(limited_candidates),
                    "evidence_before": len(evidence_items),
                    "evidence_after": len(limited_evidence),
                },
            )
        )
    return limited_candidates, limited_evidence, diagnostics, partial


def _derive_retrieval_status(
    *,
    candidates: Sequence[RetrievalCandidate],
    evidence_items: Sequence[RetrievalEvidence],
    source_usage: Sequence[RetrievalSourceUsage],
    diagnostics: Sequence[RetrievalDiagnostic],
    source_partial: bool,
    budget_partial: bool,
) -> RetrievalStatus:
    if any(item.severity == "error" for item in diagnostics):
        return "error"

    has_empty = not candidates and not evidence_items
    if not has_empty:
        return "partial" if source_partial or budget_partial else "ok"

    statuses = {item.selection_status for item in source_usage}
    blocked_statuses = {"blocked_policy", "blocked_budget", "blocked_nondeterministic"}
    non_matching_statuses = {"out_of_scope", "out_of_target"}

    if statuses & blocked_statuses:
        return "blocked"
    if source_partial or budget_partial:
        return "partial"
    if statuses and statuses.issubset(non_matching_statuses):
        return "partial"
    if any(item.selection_status == "selected" for item in source_usage):
        return "ok"
    if diagnostics:
        return "partial"
    return "error"


def run_retrieval(request: RetrievalRequest, context: RetrievalContext) -> RetrievalOutcome:
    diagnostics: list[RetrievalDiagnostic] = []
    if not request.query_terms:
        diagnostics.append(
            RetrievalDiagnostic(
                code="request_missing_query_terms",
                message="query_terms must not be empty.",
                severity="error",
            )
        )
        return RetrievalOutcome(
            retrieval_contract_version=RETRIEVAL_CONTRACT_VERSION,
            candidates=tuple(),
            evidence_items=tuple(),
            retrieval_diagnostics=tuple(diagnostics),
            source_usage=tuple(),
            status="error",
            workspace_snapshot_id=context.workspace_snapshot_id,
            run_id=context.run_id,
            trace_id=context.trace_id,
        )

    selected_sources, source_usage_seed, source_diags, source_partial = _select_sources(request, context)
    diagnostics.extend(source_diags)

    if not selected_sources:
        statuses = {item.selection_status for item in source_usage_seed}
        blocked_statuses = {"blocked_policy", "blocked_budget", "blocked_nondeterministic"}
        non_matching_statuses = {"out_of_scope", "out_of_target"}
        if not context.sources:
            diagnostics.append(
                RetrievalDiagnostic(
                    code="no_retrieval_sources_configured",
                    message="No retrieval sources are configured in context.",
                    severity="error",
                )
            )
        elif statuses and statuses.issubset(non_matching_statuses):
            diagnostics.append(
                RetrievalDiagnostic(
                    code="no_sources_matching_scope_or_target",
                    message="No retrieval sources matched source_scope/target_scope constraints.",
                    severity="warning",
                    context={"selection_statuses": tuple(sorted(statuses))},
                )
            )
        elif statuses & blocked_statuses:
            diagnostics.append(
                RetrievalDiagnostic(
                    code="no_sources_selected_due_to_constraints",
                    message="No retrieval sources selected due to policy/budget constraints.",
                    severity="warning",
                    context={"selection_statuses": tuple(sorted(statuses & blocked_statuses))},
                )
            )
        elif not diagnostics:
            diagnostics.append(
                RetrievalDiagnostic(
                    code="no_sources_selected",
                    message="No retrieval sources available for request.",
                    severity="error",
                )
            )
        status = _derive_retrieval_status(
            candidates=tuple(),
            evidence_items=tuple(),
            source_usage=source_usage_seed,
            diagnostics=diagnostics,
            source_partial=source_partial,
            budget_partial=False,
        )
        return RetrievalOutcome(
            retrieval_contract_version=RETRIEVAL_CONTRACT_VERSION,
            candidates=tuple(),
            evidence_items=tuple(),
            retrieval_diagnostics=tuple(diagnostics),
            source_usage=source_usage_seed,
            status=status,
            workspace_snapshot_id=context.workspace_snapshot_id,
            run_id=context.run_id,
            trace_id=context.trace_id,
        )

    candidates_raw, evidence_raw, source_usage = _generate_candidates_and_evidence(
        request,
        selected_sources,
        context,
        source_usage_seed,
    )
    candidates_deduped, candidate_dedupe_diags = _dedupe_candidates(candidates_raw)
    evidence_deduped, evidence_dedupe_diags = _dedupe_evidence(evidence_raw)
    diagnostics.extend(candidate_dedupe_diags)
    diagnostics.extend(evidence_dedupe_diags)

    candidates_limited, evidence_limited, budget_diags, budget_partial = _apply_budget_limits(
        request, candidates_deduped, evidence_deduped
    )
    diagnostics.extend(budget_diags)
    if not candidates_limited and not evidence_limited:
        if budget_partial:
            diagnostics.append(
                RetrievalDiagnostic(
                    code="retrieval_emptied_by_budget",
                    message="All retrieval results were removed by budget limits.",
                    severity="warning",
                )
            )
        else:
            diagnostics.append(
                RetrievalDiagnostic(
                    code="no_retrieval_matches",
                    message="No retrieval candidates or evidence matched the query terms.",
                    severity="info",
                )
            )
    status = _derive_retrieval_status(
        candidates=candidates_limited,
        evidence_items=evidence_limited,
        source_usage=source_usage,
        diagnostics=diagnostics,
        source_partial=source_partial,
        budget_partial=budget_partial,
    )

    return RetrievalOutcome(
        retrieval_contract_version=RETRIEVAL_CONTRACT_VERSION,
        candidates=candidates_limited,
        evidence_items=evidence_limited,
        retrieval_diagnostics=tuple(diagnostics),
        source_usage=source_usage,
        status=status,
        workspace_snapshot_id=context.workspace_snapshot_id,
        run_id=context.run_id,
        trace_id=context.trace_id,
    )


__all__ = [
    "BudgetView",
    "PolicyContext",
    "QueryTermSignal",
    "RETRIEVAL_CONTRACT_VERSION",
    "RetrievalCandidate",
    "RetrievalContext",
    "RetrievalDiagnostic",
    "RetrievalEvidence",
    "RetrievalOutcome",
    "RetrievalRequest",
    "RetrievalSourceAdapter",
    "RetrievalSourceUsage",
    "SourceDocument",
    "run_retrieval",
]

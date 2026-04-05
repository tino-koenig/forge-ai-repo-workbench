"""Mode Execution Foundation (01): declarative stage runner with typed contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Callable, Literal, Mapping

StageStatus = Literal["ok", "noop", "blocked", "error"]
TerminalStatus = Literal["ok", "blocked", "error"]
SideEffectClass = Literal["none", "read", "write"]


@dataclass(frozen=True)
class StageDiagnostic:
    code: str
    message: str


@dataclass(frozen=True)
class ExecutionContext:
    request: Mapping[str, object]
    settings: Mapping[str, object]
    settings_snapshot_id: str
    budget_state_ref: Mapping[str, object]
    obs_context: Mapping[str, object]
    contract_context: Mapping[str, object]
    run_id: str
    trace_id: str
    iteration_id: str | None = None
    now_ms: Callable[[], int] = field(default=lambda: int(time() * 1000))


@dataclass(frozen=True)
class ExecutionState:
    domain_state: Mapping[str, object] = field(default_factory=dict)
    iteration_state: Mapping[str, object] = field(default_factory=dict)
    diagnostics: tuple[StageDiagnostic, ...] = tuple()
    section_contributions: Mapping[str, tuple[object, ...]] = field(default_factory=dict)
    terminal_status: TerminalStatus | None = None
    done_reason: str | None = None


@dataclass(frozen=True)
class StageResult:
    stage_name: str
    stage_id: str
    status: StageStatus
    side_effect_class: SideEffectClass
    state_delta: Mapping[str, object] = field(default_factory=dict)
    budget_delta: Mapping[str, object] = field(default_factory=dict)
    diagnostics: tuple[StageDiagnostic, ...] = tuple()
    section_contributions: Mapping[str, tuple[object, ...]] = field(default_factory=dict)
    evidence_delta: Mapping[str, object] = field(default_factory=dict)
    next_actions_hint: tuple[str, ...] = tuple()
    policy_events: tuple[Mapping[str, object], ...] = tuple()
    done_reason_hint: str | None = None

    def __post_init__(self) -> None:
        allowed_status = {"ok", "noop", "blocked", "error"}
        if self.status not in allowed_status:
            raise ValueError(f"Invalid stage status '{self.status}'.")
        allowed_side_effect_class = {"none", "read", "write"}
        if self.side_effect_class not in allowed_side_effect_class:
            raise ValueError(f"Invalid side_effect_class '{self.side_effect_class}'.")


StageHandler = Callable[[ExecutionContext, ExecutionState], StageResult]


@dataclass(frozen=True)
class StageDefinition:
    stage_name: str
    stage_id: str
    side_effect_class: SideEffectClass
    handler: StageHandler


@dataclass(frozen=True)
class ModeExecutionPlan:
    mode_name: str
    stages: tuple[StageDefinition, ...]

    def __post_init__(self) -> None:
        if len(self.stages) < 2:
            raise ValueError("ModeExecutionPlan requires at least init and finalize stages.")

        names = [stage.stage_name for stage in self.stages]
        if names[0] != "init" or names[-1] != "finalize":
            raise ValueError("Plan must start with init and end with finalize.")
        if names.count("init") != 1 or names.count("finalize") != 1:
            raise ValueError("Plan must contain init/finalize exactly once.")

        stage_ids = [stage.stage_id for stage in self.stages]
        if len(stage_ids) != len(set(stage_ids)):
            raise ValueError("Stage IDs must be unique in plan.")


@dataclass(frozen=True)
class TraceEntry:
    run_id: str
    trace_id: str
    iteration_id: str | None
    stage_name: str
    stage_id: str
    status: StageStatus
    duration_ms: int
    state_delta_summary: tuple[str, ...]
    budget_delta_summary: tuple[str, ...]
    diagnostics_count: int
    settings_snapshot_id: str


@dataclass(frozen=True)
class ExecutionOutcome:
    mode_name: str
    state: ExecutionState
    stage_results: tuple[StageResult, ...]
    trace: tuple[TraceEntry, ...]
    terminal_status: TerminalStatus | None
    done_reason: str | None


def _merge_mapping(current: Mapping[str, object], delta: Mapping[str, object]) -> dict[str, object]:
    merged: dict[str, object] = dict(current)
    for key, value in delta.items():
        existing = merged.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            merged[key] = _merge_mapping(existing, value)
        else:
            merged[key] = value
    return merged


def apply_stage_result(state: ExecutionState, result: StageResult) -> ExecutionState:
    state_delta = dict(result.state_delta)

    domain_delta = state_delta.pop("domain_state", {})
    iteration_delta = state_delta.pop("iteration_state", {})

    # finalize must not introduce new domain or iteration findings.
    if result.stage_name == "finalize":
        if domain_delta:
            domain_delta = {}
        if iteration_delta:
            iteration_delta = {}

    terminal_status = state_delta.pop("terminal_status", state.terminal_status)
    done_reason = state_delta.pop("done_reason", state.done_reason)

    merged_domain = _merge_mapping(state.domain_state, domain_delta if isinstance(domain_delta, Mapping) else {})
    merged_iteration = _merge_mapping(
        state.iteration_state,
        iteration_delta if isinstance(iteration_delta, Mapping) else {},
    )

    merged_sections: dict[str, tuple[object, ...]] = {
        key: tuple(value) for key, value in state.section_contributions.items()
    }
    for section_key, contributions in result.section_contributions.items():
        existing = merged_sections.get(section_key, tuple())
        merged_sections[section_key] = existing + tuple(contributions)

    merged_diagnostics = state.diagnostics + tuple(result.diagnostics)

    return ExecutionState(
        domain_state=merged_domain,
        iteration_state=merged_iteration,
        diagnostics=merged_diagnostics,
        section_contributions=merged_sections,
        terminal_status=terminal_status,
        done_reason=done_reason,
    )


def _blocked_skip_result(stage: StageDefinition, reason: str, upstream_status: StageStatus) -> StageResult:
    if upstream_status == "error":
        code = "stage_skipped_upstream_error"
    elif upstream_status == "blocked":
        code = "stage_skipped_upstream_blocked"
    else:
        code = "stage_skipped"
    return StageResult(
        stage_name=stage.stage_name,
        stage_id=stage.stage_id,
        status="blocked",
        side_effect_class=stage.side_effect_class,
        diagnostics=(
            StageDiagnostic(
                code=code,
                message=reason,
            ),
        ),
    )


def _trace_entry(
    context: ExecutionContext,
    stage_result: StageResult,
    duration_ms: int,
) -> TraceEntry:
    return TraceEntry(
        run_id=context.run_id,
        trace_id=context.trace_id,
        iteration_id=context.iteration_id,
        stage_name=stage_result.stage_name,
        stage_id=stage_result.stage_id,
        status=stage_result.status,
        duration_ms=duration_ms,
        state_delta_summary=tuple(sorted(stage_result.state_delta.keys())),
        budget_delta_summary=tuple(sorted(stage_result.budget_delta.keys())),
        diagnostics_count=len(stage_result.diagnostics),
        settings_snapshot_id=context.settings_snapshot_id,
    )


def _run_declared_stage(
    stage: StageDefinition,
    context: ExecutionContext,
    state: ExecutionState,
) -> StageResult:
    try:
        result = stage.handler(context, state)
    except Exception as exc:
        return StageResult(
            stage_name=stage.stage_name,
            stage_id=stage.stage_id,
            status="error",
            side_effect_class=stage.side_effect_class,
            diagnostics=(
                StageDiagnostic(
                    code="stage_exception",
                    message=f"{stage.stage_name} failed with exception: {exc}",
                ),
            ),
        )

    if result.stage_name != stage.stage_name or result.stage_id != stage.stage_id:
        return StageResult(
            stage_name=stage.stage_name,
            stage_id=stage.stage_id,
            status="error",
            side_effect_class=stage.side_effect_class,
            diagnostics=(
                StageDiagnostic(
                    code="undeclared_stage_result",
                    message="Stage result does not match declared stage identity.",
                ),
            ),
        )

    if result.side_effect_class != stage.side_effect_class:
        return StageResult(
            stage_name=stage.stage_name,
            stage_id=stage.stage_id,
            status="error",
            side_effect_class=stage.side_effect_class,
            diagnostics=(
                StageDiagnostic(
                    code="side_effect_class_mismatch",
                    message=(
                        "Stage result side_effect_class does not match plan declaration "
                        f"({result.side_effect_class} != {stage.side_effect_class})."
                    ),
                ),
            ),
        )

    return result


def run_mode(plan: ModeExecutionPlan, context: ExecutionContext) -> ExecutionOutcome:
    state = ExecutionState()
    stage_results: list[StageResult] = []
    trace: list[TraceEntry] = []

    stage_defs = list(plan.stages)
    non_finalize = stage_defs[:-1]
    finalize_stage = stage_defs[-1]

    blocked_rest = False
    upstream_failure_status: StageStatus | None = None
    skip_reason = ""

    for stage in non_finalize:
        if blocked_rest:
            result = _blocked_skip_result(stage, skip_reason, upstream_failure_status or "blocked")
            started = context.now_ms()
            finished = context.now_ms()
        else:
            started = context.now_ms()
            result = _run_declared_stage(stage, context, state)
            finished = context.now_ms()
            if result.status in ("error", "blocked"):
                blocked_rest = True
                upstream_failure_status = result.status
                skip_reason = f"Skipped due to upstream stage status={result.status}"

        state = apply_stage_result(state, result)
        stage_results.append(result)
        trace.append(_trace_entry(context, result, max(0, finished - started)))

    started = context.now_ms()
    finalize_result = _run_declared_stage(finalize_stage, context, state)
    finished = context.now_ms()
    state = apply_stage_result(state, finalize_result)
    stage_results.append(finalize_result)
    trace.append(_trace_entry(context, finalize_result, max(0, finished - started)))

    return ExecutionOutcome(
        mode_name=plan.mode_name,
        state=state,
        stage_results=tuple(stage_results),
        trace=tuple(trace),
        terminal_status=state.terminal_status,
        done_reason=state.done_reason,
    )


__all__ = [
    "ExecutionContext",
    "ExecutionOutcome",
    "ExecutionState",
    "ModeExecutionPlan",
    "SideEffectClass",
    "TerminalStatus",
    "StageDefinition",
    "StageDiagnostic",
    "StageResult",
    "StageStatus",
    "TraceEntry",
    "apply_stage_result",
    "run_mode",
]

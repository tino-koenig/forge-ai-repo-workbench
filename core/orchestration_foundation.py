"""Orchestration Foundation (02): deterministic orchestration control over iterative runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Literal, Mapping

DecisionValue = Literal["continue", "stop"]
ControlSignal = Literal["none", "replan", "recover", "handoff", "block"]
DecisionConfidence = Literal["low", "medium", "high"]
DoneReason = Literal["sufficient_evidence", "no_progress", "budget_exhausted", "policy_blocked", "error"]
LifecycleState = Literal["initialized", "running", "blocked", "terminal_success", "terminal_failure"]
ActionStatus = Literal["ok", "noop", "blocked", "error"]
DecisionSource = Literal["deterministic", "llm", "fallback"]
FailureCategory = Literal["transient_error", "policy_error", "budget_error", "logic_error"]
DiagnosticSeverity = Literal["info", "warning", "error"]

_DONE_REASON_PRIORITY: tuple[DoneReason, ...] = (
    "error",
    "policy_blocked",
    "budget_exhausted",
    "no_progress",
    "sufficient_evidence",
)

_ALLOWED_TRANSITIONS: tuple[tuple[LifecycleState, LifecycleState], ...] = (
    ("initialized", "running"),
    ("running", "running"),
    ("running", "blocked"),
    ("running", "terminal_success"),
    ("running", "terminal_failure"),
    ("blocked", "running"),
    ("blocked", "terminal_failure"),
)

CONFIDENCE_HIGH_MIN_SCORE = 1.0
CONFIDENCE_MEDIUM_MIN_SCORE = 0.2


def _stable_hash(value: Mapping[str, object]) -> str:
    normalized = _normalize_mapping(value)
    canonical_json = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(canonical_json.encode("utf-8")).hexdigest()


def _normalize_mapping(value: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key in sorted(value.keys()):
        item = value[key]
        if isinstance(item, Mapping):
            result[key] = _normalize_mapping(item)
        elif isinstance(item, tuple):
            result[key] = list(item)
        elif isinstance(item, list):
            normalized_list: list[object] = []
            for entry in item:
                if isinstance(entry, Mapping):
                    normalized_list.append(_normalize_mapping(entry))
                else:
                    normalized_list.append(entry)
            result[key] = normalized_list
        else:
            result[key] = item
    return result


@dataclass(frozen=True)
class OrchestrationDiagnostic:
    code: str
    message: str
    severity: DiagnosticSeverity


@dataclass(frozen=True)
class ProgressSignal:
    evidence_gain: int
    confidence_gain: float
    top_candidate_changed: bool
    score_gain: float


@dataclass(frozen=True)
class ProgressEvaluation:
    score: float
    components: Mapping[str, float]
    no_progress: bool
    confidence: DecisionConfidence


@dataclass(frozen=True)
class ObjectiveSpec:
    objective_id: str
    objective_type: str
    acceptance_gates: tuple[str, ...]
    hard_fail_gates: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.objective_id:
            raise ValueError("objective_id is required.")
        if not self.objective_type:
            raise ValueError("objective_type is required.")


@dataclass(frozen=True)
class HandoffPacket:
    handoff_id: str
    source_mode: str
    target_mode: str
    reason: str
    constraints: Mapping[str, object]
    evidence_bundle: tuple[Mapping[str, object], ...]
    acceptance_gates: tuple[str, ...]
    max_loop_count: int

    def __post_init__(self) -> None:
        if not self.handoff_id:
            raise ValueError("handoff_id is required.")
        if not self.source_mode or not self.target_mode:
            raise ValueError("source_mode and target_mode are required.")
        if not self.acceptance_gates:
            raise ValueError("acceptance_gates must not be empty.")
        if self.max_loop_count < 1:
            raise ValueError("max_loop_count must be >= 1.")


@dataclass(frozen=True)
class OrchestrationDecision:
    # decision answers "continue vs stop".
    # control_signal refines *how* continuation happens: none|replan|recover|handoff|block.
    decision: DecisionValue
    next_action: str | None
    reason: str
    confidence: DecisionConfidence
    control_signal: ControlSignal
    done_reason: DoneReason | None
    decision_source: DecisionSource
    alternative_actions: tuple[str, ...] = tuple()
    replan_trigger: str | None = None
    diagnostics: tuple[OrchestrationDiagnostic, ...] = tuple()


@dataclass(frozen=True)
class IterationInput:
    iteration_id: str
    next_action: str | None
    action_input_hash: str
    action_status: ActionStatus
    budget_before: float
    budget_after: float
    actual_cost: float
    progress_signal: ProgressSignal
    sufficient_evidence: bool = False
    policy_blocked: bool = False
    policy_recoverable: bool = False
    budget_recoverable: bool = False
    failure_category: FailureCategory | None = None
    requested_handoff: HandoffPacket | None = None
    replan_candidate_action: str | None = None
    objective_gate_missed: bool = False
    new_evidence_conflict: bool = False
    settings_snapshot_id: str = "settings-unknown"
    policy_version: str = "policy-unknown"
    causal_parent_id: str | None = None


@dataclass(frozen=True)
class OrchestrationState:
    run_id: str
    trace_id: str
    objective: ObjectiveSpec
    lifecycle_state: LifecycleState = "initialized"
    iteration_count: int = 0
    done_reason: DoneReason | None = None
    no_progress_streak: int = 0
    max_no_progress_streak: int = 2
    replan_count: int = 0
    max_replans: int = 1
    action_repeat_limit: int = 2
    action_fingerprint_counts: Mapping[str, int] = field(default_factory=dict)
    last_state_payload: Mapping[str, object] = field(default_factory=dict)
    handoff_loop_count: int = 0


@dataclass(frozen=True)
class OrchestrationTraceEntry:
    run_id: str
    trace_id: str
    iteration_id: str
    decision: DecisionValue
    reason: str
    confidence: DecisionConfidence
    control_signal: ControlSignal
    action_status: ActionStatus
    budget_before: float
    budget_after: float
    progress_score: float
    progress_components: Mapping[str, float]
    done_reason: DoneReason | None
    causal_parent_id: str | None
    action_input_hash: str
    state_hash_before: str
    state_hash_after: str
    settings_snapshot_id: str
    policy_version: str
    decision_source: DecisionSource
    actual_cost: float
    recovery_step: bool
    decision_diagnostic_codes: tuple[str, ...] = tuple()


def choose_done_reason(candidates: Mapping[DoneReason, bool]) -> DoneReason | None:
    for reason in _DONE_REASON_PRIORITY:
        if candidates.get(reason, False):
            return reason
    return None


def evaluate_progress_signal(signal: ProgressSignal) -> ProgressEvaluation:
    components: dict[str, float] = {
        "evidence_gain": float(signal.evidence_gain),
        "confidence_gain": float(signal.confidence_gain),
        "score_gain": float(signal.score_gain),
        "candidate_shift": 1.0 if signal.top_candidate_changed else 0.0,
    }
    score = (
        components["evidence_gain"] * 0.35
        + components["confidence_gain"] * 0.30
        + components["score_gain"] * 0.25
        + components["candidate_shift"] * 0.10
    )
    no_progress = (
        signal.evidence_gain <= 0
        and signal.confidence_gain <= 0.0
        and signal.score_gain <= 0.0
        and not signal.top_candidate_changed
    )
    # Confidence is a deterministic heuristic derived from progress score (not an independent estimate).
    if score >= CONFIDENCE_HIGH_MIN_SCORE:
        confidence: DecisionConfidence = "high"
    elif score >= CONFIDENCE_MEDIUM_MIN_SCORE:
        confidence = "medium"
    else:
        confidence = "low"
    return ProgressEvaluation(score=score, components=components, no_progress=no_progress, confidence=confidence)


def validate_fsm_transition(
    current_state: LifecycleState,
    next_state: LifecycleState,
    *,
    recoverable_block: bool = False,
) -> tuple[bool, OrchestrationDiagnostic | None]:
    if (current_state, next_state) not in _ALLOWED_TRANSITIONS:
        return (
            False,
            OrchestrationDiagnostic(
                code="invalid_fsm_transition",
                message=f"Transition {current_state} -> {next_state} is not allowed.",
                severity="error",
            ),
        )
    if next_state == "blocked" and not recoverable_block:
        return (
            False,
            OrchestrationDiagnostic(
                code="blocked_requires_recoverable_condition",
                message="blocked state requires recoverable condition.",
                severity="error",
            ),
        )
    return True, None


def _fingerprint(action_name: str | None, action_input_hash: str) -> str:
    return f"{action_name or '<none>'}:{action_input_hash}"


def _collect_replan_triggers(
    state: OrchestrationState, iteration: IterationInput, progress: ProgressEvaluation
) -> tuple[str, ...]:
    active: list[str] = []
    if iteration.objective_gate_missed:
        active.append("objective_gate_miss")
    if iteration.new_evidence_conflict:
        active.append("new_evidence_conflict")
    if progress.no_progress and state.no_progress_streak + 1 >= state.max_no_progress_streak:
        active.append("no_progress_streak")
    if progress.confidence == "low":
        active.append("low_confidence")
    return tuple(active)


def _decision_stop(done_reason: DoneReason, confidence: DecisionConfidence) -> OrchestrationDecision:
    return OrchestrationDecision(
        decision="stop",
        next_action=None,
        reason=f"terminal:{done_reason}",
        confidence=confidence,
        control_signal="none",
        done_reason=done_reason,
        decision_source="deterministic",
        diagnostics=tuple(),
    )


def _decide_when_blocked(state: OrchestrationState, iteration: IterationInput, progress: ProgressEvaluation) -> OrchestrationDecision:
    if state.lifecycle_state != "blocked":
        raise ValueError("_decide_when_blocked requires lifecycle_state='blocked'.")
    terminal_reason = choose_done_reason(
        {
            "error": iteration.failure_category == "logic_error",
            "policy_blocked": iteration.policy_blocked and not iteration.policy_recoverable,
            "budget_exhausted": iteration.budget_after <= 0 and not iteration.budget_recoverable,
            "no_progress": False,
            "sufficient_evidence": False,
        }
    )
    if terminal_reason is not None:
        return _decision_stop(terminal_reason, progress.confidence)

    if iteration.policy_blocked and iteration.policy_recoverable:
        return OrchestrationDecision(
            decision="continue",
            next_action=iteration.next_action,
            reason="blocked_waiting_policy_recovery",
            confidence="low",
            control_signal="block",
            done_reason=None,
            decision_source="deterministic",
            diagnostics=tuple(),
        )
    if iteration.budget_after <= 0 and iteration.budget_recoverable:
        return OrchestrationDecision(
            decision="continue",
            next_action=iteration.next_action,
            reason="blocked_waiting_budget_recovery",
            confidence="low",
            control_signal="block",
            done_reason=None,
            decision_source="deterministic",
            diagnostics=tuple(),
        )
    return OrchestrationDecision(
        decision="continue",
        next_action=iteration.next_action,
        reason="recover_from_blocked",
        confidence=progress.confidence,
        control_signal="recover",
        done_reason=None,
        decision_source="deterministic",
        diagnostics=tuple(),
    )


def _decide_terminal_reason(state: OrchestrationState, iteration: IterationInput, progress: ProgressEvaluation) -> OrchestrationDecision | None:
    done_reason = choose_done_reason(
        {
            "error": iteration.failure_category == "logic_error",
            "policy_blocked": iteration.policy_blocked and not iteration.policy_recoverable,
            "budget_exhausted": iteration.budget_after <= 0 and not iteration.budget_recoverable,
            "no_progress": progress.no_progress and (state.no_progress_streak + 1 >= state.max_no_progress_streak),
            "sufficient_evidence": iteration.sufficient_evidence,
        }
    )
    if done_reason is None:
        return None
    return _decision_stop(done_reason, progress.confidence)


def _decide_handoff(iteration: IterationInput, progress: ProgressEvaluation) -> OrchestrationDecision | None:
    if iteration.requested_handoff is None:
        return None
    return OrchestrationDecision(
        decision="continue",
        next_action=None,
        reason="handoff_requested",
        confidence=progress.confidence,
        control_signal="handoff",
        done_reason=None,
        decision_source="deterministic",
        diagnostics=tuple(),
    )


def _decide_recovery(iteration: IterationInput) -> OrchestrationDecision | None:
    if iteration.failure_category == "transient_error":
        return OrchestrationDecision(
            decision="continue",
            next_action=iteration.next_action,
            reason="recover_transient_error",
            confidence="low",
            control_signal="recover",
            done_reason=None,
            decision_source="fallback",
            diagnostics=tuple(),
        )
    if iteration.policy_blocked and iteration.policy_recoverable:
        return OrchestrationDecision(
            decision="continue",
            next_action=iteration.next_action,
            reason="block_recoverable_policy",
            confidence="low",
            control_signal="block",
            done_reason=None,
            decision_source="deterministic",
            diagnostics=tuple(),
        )
    if iteration.budget_after <= 0 and iteration.budget_recoverable:
        return OrchestrationDecision(
            decision="continue",
            next_action=iteration.next_action,
            reason="block_recoverable_budget",
            confidence="low",
            control_signal="block",
            done_reason=None,
            decision_source="fallback",
            diagnostics=tuple(),
        )
    return None


def _decide_replan(state: OrchestrationState, iteration: IterationInput, progress: ProgressEvaluation) -> OrchestrationDecision | None:
    triggers = _collect_replan_triggers(state, iteration, progress)
    if not triggers or state.replan_count >= state.max_replans or iteration.replan_candidate_action is None:
        return None
    primary_trigger = triggers[0]
    diagnostics: list[OrchestrationDiagnostic] = []
    for secondary in triggers[1:]:
        diagnostics.append(
            OrchestrationDiagnostic(
                code="replan_secondary_trigger_active",
                message=f"Secondary replan trigger also active: {secondary}.",
                severity="info",
            )
        )
    return OrchestrationDecision(
        decision="continue",
        next_action=iteration.replan_candidate_action,
        reason=f"replan:{primary_trigger}",
        confidence=progress.confidence,
        control_signal="replan",
        done_reason=None,
        decision_source="deterministic",
        replan_trigger=primary_trigger,
        diagnostics=tuple(diagnostics),
    )


def _decide_anti_loop(state: OrchestrationState, iteration: IterationInput) -> OrchestrationDecision | None:
    fingerprint = _fingerprint(iteration.next_action, iteration.action_input_hash)
    repeat_count = state.action_fingerprint_counts.get(fingerprint, 0)
    if repeat_count < state.action_repeat_limit:
        return None
    return OrchestrationDecision(
        decision="stop",
        next_action=None,
        reason="terminal:no_progress",
        confidence="low",
        control_signal="none",
        done_reason="no_progress",
        decision_source="deterministic",
        diagnostics=(
            OrchestrationDiagnostic(
                code="replan_anti_loop_exhausted",
                message="Action/input repetition exceeded allowed limit.",
                severity="error",
            ),
        ),
    )


def _decide_continue_default(iteration: IterationInput, progress: ProgressEvaluation) -> OrchestrationDecision:
    return OrchestrationDecision(
        decision="continue",
        next_action=iteration.next_action,
        reason="continue_with_progress",
        confidence=progress.confidence,
        control_signal="none",
        done_reason=None,
        decision_source="deterministic",
        diagnostics=tuple(),
    )


def decide_orchestration(state: OrchestrationState, iteration: IterationInput) -> OrchestrationDecision:
    progress = evaluate_progress_signal(iteration.progress_signal)

    if state.lifecycle_state == "blocked":
        return _decide_when_blocked(state, iteration, progress)

    terminal_decision = _decide_terminal_reason(state, iteration, progress)
    if terminal_decision is not None:
        return terminal_decision

    handoff_decision = _decide_handoff(iteration, progress)
    if handoff_decision is not None:
        return handoff_decision

    recovery_decision = _decide_recovery(iteration)
    if recovery_decision is not None:
        return recovery_decision

    replan_decision = _decide_replan(state, iteration, progress)
    if replan_decision is not None:
        return replan_decision

    anti_loop_decision = _decide_anti_loop(state, iteration)
    if anti_loop_decision is not None:
        return anti_loop_decision

    return _decide_continue_default(iteration, progress)


def _next_lifecycle_state(
    state: OrchestrationState,
    iteration: IterationInput,
    decision: OrchestrationDecision,
) -> LifecycleState:
    if decision.decision == "stop":
        if decision.done_reason == "sufficient_evidence":
            return "terminal_success"
        return "terminal_failure"
    if decision.control_signal == "block":
        if iteration.policy_recoverable or iteration.budget_recoverable:
            return "blocked"
        return "terminal_failure"
    if state.lifecycle_state == "initialized":
        return "running"
    if state.lifecycle_state == "blocked" and decision.control_signal == "recover":
        return "running"
    return "running"


def apply_orchestration_step(
    state: OrchestrationState,
    iteration: IterationInput,
    decision: OrchestrationDecision,
) -> tuple[OrchestrationState, OrchestrationTraceEntry]:
    progress = evaluate_progress_signal(iteration.progress_signal)
    before_payload = {
        "iteration_count": state.iteration_count,
        "done_reason": state.done_reason,
        "no_progress_streak": state.no_progress_streak,
        "replan_count": state.replan_count,
        "lifecycle_state": state.lifecycle_state,
        "action_fingerprint_counts": dict(state.action_fingerprint_counts),
    }

    no_progress_streak = state.no_progress_streak + 1 if progress.no_progress else 0
    replan_count = state.replan_count + 1 if decision.control_signal == "replan" else state.replan_count
    # handoff_loop_count is defined as consecutive handoff chain length.
    handoff_loop_count = state.handoff_loop_count + 1 if decision.control_signal == "handoff" else 0

    next_fingerprints = dict(state.action_fingerprint_counts)
    should_count_fingerprint = (
        iteration.next_action is not None
        and decision.control_signal != "handoff"
        and not (state.lifecycle_state == "blocked" and decision.control_signal == "recover")
    )
    if should_count_fingerprint:
        fingerprint = _fingerprint(iteration.next_action, iteration.action_input_hash)
        next_fingerprints[fingerprint] = next_fingerprints.get(fingerprint, 0) + 1

    next_lifecycle = _next_lifecycle_state(state, iteration, decision)
    recoverable_block = iteration.policy_recoverable or iteration.budget_recoverable
    valid_transition, diagnostic = validate_fsm_transition(
        state.lifecycle_state,
        next_lifecycle,
        recoverable_block=recoverable_block,
    )
    if not valid_transition:
        next_lifecycle = "terminal_failure"
        decision = OrchestrationDecision(
            decision="stop",
            next_action=None,
            reason="terminal:error",
            confidence="low",
            control_signal="none",
            done_reason="error",
            decision_source="fallback",
            diagnostics=decision.diagnostics + ((diagnostic,) if diagnostic is not None else tuple()),
        )

    if decision.control_signal == "handoff":
        if iteration.requested_handoff is None:
            decision = OrchestrationDecision(
                decision="stop",
                next_action=None,
                reason="terminal:policy_blocked",
                confidence="low",
                control_signal="none",
                done_reason="policy_blocked",
                decision_source="deterministic",
                diagnostics=decision.diagnostics
                + (
                    OrchestrationDiagnostic(
                        code="handoff_missing_packet",
                        message="Handoff requested without complete handoff packet.",
                        severity="error",
                    ),
                ),
            )
            next_lifecycle = "terminal_failure"
        elif handoff_loop_count > iteration.requested_handoff.max_loop_count:
            decision = OrchestrationDecision(
                decision="stop",
                next_action=None,
                reason="terminal:policy_blocked",
                confidence="low",
                control_signal="none",
                done_reason="policy_blocked",
                decision_source="deterministic",
                diagnostics=decision.diagnostics
                + (
                    OrchestrationDiagnostic(
                        code="handoff_loop_limit_exceeded",
                        message="Handoff loop count exceeded max_loop_count.",
                        severity="error",
                    ),
                ),
            )
            next_lifecycle = "terminal_failure"

    after_payload = {
        "iteration_count": state.iteration_count + 1,
        "done_reason": decision.done_reason if decision.decision == "stop" else state.done_reason,
        "no_progress_streak": no_progress_streak,
        "replan_count": replan_count,
        "lifecycle_state": next_lifecycle,
        "action_fingerprint_counts": dict(next_fingerprints),
    }
    next_state = OrchestrationState(
        run_id=state.run_id,
        trace_id=state.trace_id,
        objective=state.objective,
        lifecycle_state=next_lifecycle,
        iteration_count=state.iteration_count + 1,
        done_reason=decision.done_reason if decision.decision == "stop" else state.done_reason,
        no_progress_streak=no_progress_streak,
        max_no_progress_streak=state.max_no_progress_streak,
        replan_count=replan_count,
        max_replans=state.max_replans,
        action_repeat_limit=state.action_repeat_limit,
        action_fingerprint_counts=next_fingerprints,
        last_state_payload=after_payload,
        handoff_loop_count=handoff_loop_count,
    )

    trace = OrchestrationTraceEntry(
        run_id=state.run_id,
        trace_id=state.trace_id,
        iteration_id=iteration.iteration_id,
        decision=decision.decision,
        reason=decision.reason,
        confidence=decision.confidence,
        control_signal=decision.control_signal,
        action_status=iteration.action_status,
        budget_before=iteration.budget_before,
        budget_after=iteration.budget_after,
        progress_score=progress.score,
        progress_components=dict(progress.components),
        done_reason=decision.done_reason if decision.decision == "stop" else state.done_reason,
        causal_parent_id=iteration.causal_parent_id,
        action_input_hash=iteration.action_input_hash,
        state_hash_before=_stable_hash(before_payload),
        state_hash_after=_stable_hash(after_payload),
        settings_snapshot_id=iteration.settings_snapshot_id,
        policy_version=iteration.policy_version,
        decision_source=decision.decision_source,
        actual_cost=iteration.actual_cost,
        recovery_step=decision.control_signal == "recover",
        decision_diagnostic_codes=tuple(diagnostic.code for diagnostic in decision.diagnostics),
    )
    return next_state, trace


__all__ = [
    "ActionStatus",
    "ControlSignal",
    "DecisionConfidence",
    "DecisionSource",
    "DoneReason",
    "FailureCategory",
    "HandoffPacket",
    "IterationInput",
    "LifecycleState",
    "ObjectiveSpec",
    "OrchestrationDecision",
    "OrchestrationDiagnostic",
    "OrchestrationState",
    "OrchestrationTraceEntry",
    "ProgressEvaluation",
    "ProgressSignal",
    "apply_orchestration_step",
    "choose_done_reason",
    "decide_orchestration",
    "evaluate_progress_signal",
    "validate_fsm_transition",
]

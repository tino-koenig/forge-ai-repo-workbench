"""Observability Foundation (11): structured, correlatable event telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from itertools import count
import json
from typing import Callable, Literal, Mapping, Sequence

ObsLevel = Literal["minimal", "standard", "debug"]
RedactionStatus = Literal["not_needed", "applied", "blocked", "failed"]

EVENT_SCHEMA_VERSION = "11.1"
EVENT_CATALOG_VERSION = "11.1"
DEFAULT_RETENTION_SECONDS = 7 * 24 * 60 * 60

EVENT_RUN_STARTED = "run_started"
EVENT_RUN_FINISHED = "run_finished"
EVENT_STAGE_STARTED = "stage_started"
EVENT_STAGE_FINISHED = "stage_finished"
EVENT_STAGE_FAILED = "stage_failed"
EVENT_ACTION_PLANNED = "action_planned"
EVENT_ACTION_EXECUTED = "action_executed"
EVENT_ACTION_NOOP = "action_noop"
EVENT_ACTION_BLOCKED = "action_blocked"
EVENT_DECISION_MADE = "decision_made"
EVENT_FALLBACK_APPLIED = "fallback_applied"
EVENT_BUDGET_SNAPSHOT = "budget_snapshot"
EVENT_BUDGET_EXHAUSTED = "budget_exhausted"
EVENT_POLICY_CHECK = "policy_check"
EVENT_POLICY_BLOCKED = "policy_blocked"

EVENT_TYPES: tuple[str, ...] = (
    EVENT_RUN_STARTED,
    EVENT_RUN_FINISHED,
    EVENT_STAGE_STARTED,
    EVENT_STAGE_FINISHED,
    EVENT_STAGE_FAILED,
    EVENT_ACTION_PLANNED,
    EVENT_ACTION_EXECUTED,
    EVENT_ACTION_NOOP,
    EVENT_ACTION_BLOCKED,
    EVENT_DECISION_MADE,
    EVENT_FALLBACK_APPLIED,
    EVENT_BUDGET_SNAPSHOT,
    EVENT_BUDGET_EXHAUSTED,
    EVENT_POLICY_CHECK,
    EVENT_POLICY_BLOCKED,
)

ORCHESTRATION_EVENT_PREFIXES: tuple[str, ...] = ("action_", "decision_", "budget_", "policy_")
SENSITIVE_KEY_FRAGMENTS: tuple[str, ...] = ("secret", "token", "password", "api_key", "authorization")


def _iso_utc(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_payload(payload: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key in sorted(payload.keys()):
        value = payload[key]
        normalized[key] = _normalize_value(value)
    return normalized


def _normalize_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _normalize_payload(value)
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_value(item) for item in value]
    return value


def _contains_unredacted_sensitive_value(payload: Mapping[str, object]) -> bool:
    for key, value in payload.items():
        lowered = key.lower()
        if any(fragment in lowered for fragment in SENSITIVE_KEY_FRAGMENTS):
            if not (isinstance(value, str) and value == "[REDACTED]"):
                return True
        if isinstance(value, Mapping) and _contains_unredacted_sensitive_value(value):
            return True
        if isinstance(value, list):
            for item in value:
                if isinstance(item, Mapping) and _contains_unredacted_sensitive_value(item):
                    return True
    return False


def _hash_state(payload: Mapping[str, object]) -> str:
    normalized = _normalize_payload(payload)
    canonical_json = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    canonical = canonical_json.encode("utf-8")
    return sha256(canonical).hexdigest()


@dataclass(frozen=True)
class ObsContext:
    capability: str
    profile: str
    source_component: str
    session_id: str | None = None
    parent_run_id: str | None = None
    level: ObsLevel = "minimal"
    retention_seconds: int = DEFAULT_RETENTION_SECONDS
    now: Callable[[], datetime] = field(default=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.level not in ("minimal", "standard", "debug"):
            raise ValueError(f"Invalid observability level '{self.level}'.")
        if self.retention_seconds <= 0:
            raise ValueError("retention_seconds must be > 0.")


@dataclass(frozen=True)
class ObsEvent:
    event_id: str
    event_type: str
    timestamp: str
    run_id: str
    capability: str
    profile: str
    source_component: str
    payload: Mapping[str, object]
    redaction_status: RedactionStatus
    event_schema_version: str = EVENT_SCHEMA_VERSION
    event_catalog_version: str = EVENT_CATALOG_VERSION
    stage_id: str | None = None
    action_id: str | None = None
    session_id: str | None = None
    iteration_id: str | None = None
    trace_id: str | None = None
    parent_run_id: str | None = None
    decision_source: str | None = None
    done_reason: str | None = None
    policy_version: str | None = None
    settings_snapshot_id: str | None = None
    action_input_hash: str | None = None
    state_hash_before: str | None = None
    state_hash_after: str | None = None
    redaction_version: str | None = None

    def __post_init__(self) -> None:
        if self.event_type not in EVENT_TYPES:
            raise ValueError(f"Unknown event_type '{self.event_type}'.")
        if self.redaction_status not in ("not_needed", "applied", "blocked", "failed"):
            raise ValueError(f"Invalid redaction_status '{self.redaction_status}'.")
        if not isinstance(self.payload, Mapping):
            raise ValueError("payload must be a mapping.")
        if self.trace_id is None:
            raise ValueError("trace_id is required.")

        if _contains_unredacted_sensitive_value(self.payload):
            raise ValueError("payload contains unredacted sensitive data.")

        if self.redaction_status == "applied" and not self.redaction_version:
            raise ValueError("redaction_version is required when redaction_status='applied'.")

        if self._is_orchestration_event():
            if self.iteration_id is None:
                raise ValueError("iteration_id is required for orchestration events.")
            if self.trace_id is None:
                raise ValueError("trace_id is required for orchestration events.")
            if self.policy_version is None:
                raise ValueError("policy_version is required for orchestration events.")
            if self.settings_snapshot_id is None:
                raise ValueError("settings_snapshot_id is required for orchestration events.")

        if self.event_type.startswith("action_") and self.action_input_hash is None:
            raise ValueError("action_input_hash is required for action events.")

    def _is_orchestration_event(self) -> bool:
        return any(self.event_type.startswith(prefix) for prefix in ORCHESTRATION_EVENT_PREFIXES)

    def as_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "event_schema_version": self.event_schema_version,
            "event_catalog_version": self.event_catalog_version,
            "run_id": self.run_id,
            "stage_id": self.stage_id,
            "action_id": self.action_id,
            "session_id": self.session_id,
            "iteration_id": self.iteration_id,
            "trace_id": self.trace_id,
            "parent_run_id": self.parent_run_id,
            "capability": self.capability,
            "profile": self.profile,
            "source_component": self.source_component,
            "decision_source": self.decision_source,
            "done_reason": self.done_reason,
            "policy_version": self.policy_version,
            "settings_snapshot_id": self.settings_snapshot_id,
            "action_input_hash": self.action_input_hash,
            "state_hash_before": self.state_hash_before,
            "state_hash_after": self.state_hash_after,
            "payload": _normalize_payload(self.payload),
            "redaction_status": self.redaction_status,
            "redaction_version": self.redaction_version,
        }


@dataclass(frozen=True)
class ObsRunSummary:
    run_id: str
    capability: str
    profile: str
    started_at: str
    finished_at: str
    duration_ms: int
    total_events: int
    stage_duration_ms: Mapping[str, int]
    action_status_counts: Mapping[str, int]
    decision_source_counts: Mapping[str, int]
    budget_relevant: tuple[str, ...]
    stop_reasons: tuple[str, ...]
    replan_reasons: tuple[str, ...]
    block_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "capability": self.capability,
            "profile": self.profile,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "total_events": self.total_events,
            "stage_duration_ms": dict(self.stage_duration_ms),
            "action_status_counts": dict(self.action_status_counts),
            "decision_source_counts": dict(self.decision_source_counts),
            "budget_relevant": list(self.budget_relevant),
            "stop_reasons": list(self.stop_reasons),
            "replan_reasons": list(self.replan_reasons),
            "block_reasons": list(self.block_reasons),
        }


@dataclass
class _RunRecord:
    context: ObsContext
    trace_id: str
    run_id: str
    events: list[ObsEvent] = field(default_factory=list)
    summary: ObsRunSummary | None = None


_RUN_COUNTER = count(1)
_EVENT_COUNTER = count(1)
_TRACE_COUNTER = count(1)
_RUNS: dict[str, _RunRecord] = {}
_CLOSED_RUNS: dict[str, _RunRecord] = {}


def _new_run_id() -> str:
    return f"obs-run-{next(_RUN_COUNTER):06d}"


def _new_trace_id() -> str:
    return f"trace-{next(_TRACE_COUNTER):06d}"


def _new_event_id() -> str:
    return f"evt-{next(_EVENT_COUNTER):08d}"


def _prune_retention(now: datetime) -> None:
    if not _CLOSED_RUNS:
        return
    removable: list[str] = []
    for run_id, record in _CLOSED_RUNS.items():
        if record.summary is None:
            continue
        finished_at = datetime.fromisoformat(record.summary.finished_at.replace("Z", "+00:00"))
        expiry = finished_at + timedelta(seconds=record.context.retention_seconds)
        if now > expiry:
            removable.append(run_id)
    for run_id in removable:
        del _CLOSED_RUNS[run_id]


def _apply_level_payload(level: ObsLevel, payload: Mapping[str, object]) -> dict[str, object]:
    normalized = _normalize_payload(payload)
    if level == "debug":
        return normalized
    if level == "standard":
        filtered = dict(normalized)
        filtered.pop("debug_details", None)
        return filtered

    filtered = dict(normalized)
    filtered.pop("debug_details", None)
    filtered.pop("verbose_context", None)
    return filtered


def _create_event(
    *,
    context: ObsContext,
    run_id: str,
    trace_id: str,
    event_type: str,
    payload: Mapping[str, object],
    redaction_status: RedactionStatus,
    stage_id: str | None = None,
    action_id: str | None = None,
    iteration_id: str | None = None,
    decision_source: str | None = None,
    done_reason: str | None = None,
    policy_version: str | None = None,
    settings_snapshot_id: str | None = None,
    action_input_hash: str | None = None,
    state_before: Mapping[str, object] | None = None,
    state_after: Mapping[str, object] | None = None,
    redaction_version: str | None = None,
) -> ObsEvent:
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be a structured mapping.")
    prepared_payload = _apply_level_payload(context.level, payload)

    state_hash_before = _hash_state(state_before) if state_before is not None else None
    state_hash_after = _hash_state(state_after) if state_after is not None else None

    return ObsEvent(
        event_id=_new_event_id(),
        timestamp=_iso_utc(context.now()),
        event_type=event_type,
        run_id=run_id,
        stage_id=stage_id,
        action_id=action_id,
        session_id=context.session_id,
        iteration_id=iteration_id,
        trace_id=trace_id,
        parent_run_id=context.parent_run_id,
        capability=context.capability,
        profile=context.profile,
        source_component=context.source_component,
        decision_source=decision_source,
        done_reason=done_reason,
        policy_version=policy_version,
        settings_snapshot_id=settings_snapshot_id,
        action_input_hash=action_input_hash,
        state_hash_before=state_hash_before,
        state_hash_after=state_hash_after,
        payload=prepared_payload,
        redaction_status=redaction_status,
        redaction_version=redaction_version,
    )


def obs_start_run(context: ObsContext) -> str:
    run_id = _new_run_id()
    trace_id = _new_trace_id()
    record = _RunRecord(context=context, trace_id=trace_id, run_id=run_id)
    _RUNS[run_id] = record

    start_event = _create_event(
        context=context,
        run_id=run_id,
        trace_id=trace_id,
        event_type=EVENT_RUN_STARTED,
        payload={"status": "started"},
        redaction_status="not_needed",
    )
    record.events.append(start_event)
    _prune_retention(context.now())
    return run_id


def obs_log_event(event: ObsEvent) -> None:
    record = _RUNS.get(event.run_id)
    if record is None:
        raise ValueError(f"Unknown or closed run_id '{event.run_id}'.")
    if event.capability != record.context.capability:
        raise ValueError(
            f"Event capability '{event.capability}' does not match run capability '{record.context.capability}'."
        )
    if event.profile != record.context.profile:
        raise ValueError(f"Event profile '{event.profile}' does not match run profile '{record.context.profile}'.")
    if event.source_component != record.context.source_component:
        raise ValueError(
            "Event source_component "
            f"'{event.source_component}' does not match run source_component '{record.context.source_component}'."
        )
    if event.trace_id != record.trace_id:
        raise ValueError(f"Event trace_id '{event.trace_id}' does not match run trace_id '{record.trace_id}'.")
    record.events.append(event)


def _derive_run_summary(events: Sequence[ObsEvent]) -> ObsRunSummary:
    if not events:
        raise ValueError("Cannot derive summary without events.")
    start_event = events[0]
    end_event = events[-1]

    if start_event.event_type != EVENT_RUN_STARTED:
        raise ValueError("Run summary derivation requires first event to be run_started.")
    if end_event.event_type != EVENT_RUN_FINISHED:
        raise ValueError("Run summary derivation requires last event to be run_finished.")

    stage_started: dict[str, datetime] = {}
    stage_duration_ms: dict[str, int] = {}
    action_status_counts: dict[str, int] = {"planned": 0, "executed": 0, "noop": 0, "blocked": 0}
    decision_source_counts: dict[str, int] = {}
    budget_relevant: set[str] = set()
    stop_reasons: list[str] = []
    replan_reasons: list[str] = []
    block_reasons: list[str] = []
    seen_block_reasons: set[str] = set()

    def _append_block_reason(reason: object) -> None:
        if not isinstance(reason, str):
            return
        if reason in seen_block_reasons:
            return
        seen_block_reasons.add(reason)
        block_reasons.append(reason)

    for event in events:
        timestamp = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
        if event.event_type == EVENT_STAGE_STARTED and event.stage_id:
            stage_started[event.stage_id] = timestamp
        elif event.event_type in (EVENT_STAGE_FINISHED, EVENT_STAGE_FAILED) and event.stage_id:
            started = stage_started.get(event.stage_id)
            if started is not None:
                duration = int((timestamp - started).total_seconds() * 1000)
                stage_duration_ms[event.stage_id] = stage_duration_ms.get(event.stage_id, 0) + max(duration, 0)

        if event.event_type == EVENT_ACTION_PLANNED:
            action_status_counts["planned"] += 1
        elif event.event_type == EVENT_ACTION_EXECUTED:
            action_status_counts["executed"] += 1
        elif event.event_type == EVENT_ACTION_NOOP:
            action_status_counts["noop"] += 1
        elif event.event_type == EVENT_ACTION_BLOCKED:
            action_status_counts["blocked"] += 1

        if event.decision_source:
            decision_source_counts[event.decision_source] = decision_source_counts.get(event.decision_source, 0) + 1

        if event.event_type in (EVENT_BUDGET_SNAPSHOT, EVENT_BUDGET_EXHAUSTED):
            budget_name = event.payload.get("budget_name")
            if isinstance(budget_name, str):
                budget_relevant.add(budget_name)

        if event.event_type == EVENT_DECISION_MADE:
            decision = event.payload.get("decision")
            control_signal = event.payload.get("control_signal")
            reason = event.payload.get("reason_code")
            if decision == "stop" and isinstance(reason, str):
                stop_reasons.append(reason)
            if control_signal == "replan" and isinstance(reason, str):
                replan_reasons.append(reason)
        elif event.event_type in (EVENT_ACTION_BLOCKED, EVENT_POLICY_BLOCKED):
            _append_block_reason(event.payload.get("reason_code"))

    started_at = datetime.fromisoformat(start_event.timestamp.replace("Z", "+00:00"))
    finished_at = datetime.fromisoformat(end_event.timestamp.replace("Z", "+00:00"))
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    return ObsRunSummary(
        run_id=start_event.run_id,
        capability=start_event.capability,
        profile=start_event.profile,
        started_at=start_event.timestamp,
        finished_at=end_event.timestamp,
        duration_ms=max(duration_ms, 0),
        total_events=len(events),
        stage_duration_ms=dict(sorted(stage_duration_ms.items())),
        action_status_counts=action_status_counts,
        decision_source_counts=dict(sorted(decision_source_counts.items())),
        budget_relevant=tuple(sorted(budget_relevant)),
        stop_reasons=tuple(stop_reasons),
        replan_reasons=tuple(replan_reasons),
        block_reasons=tuple(block_reasons),
    )


def _extract_done_reason(end_summary: Mapping[str, object] | None) -> str | None:
    if end_summary is None:
        return None
    allowed_keys = {"done_reason"}
    unknown_keys = sorted(set(end_summary.keys()) - allowed_keys)
    if unknown_keys:
        joined = ", ".join(unknown_keys)
        raise ValueError(f"obs_end_run summary supports only 'done_reason'. Unknown keys: {joined}")
    done_reason_raw = end_summary.get("done_reason")
    if done_reason_raw is None:
        return None
    if not isinstance(done_reason_raw, str):
        raise ValueError("obs_end_run summary.done_reason must be a string when provided.")
    return done_reason_raw


def obs_end_run(run_id: str, summary: Mapping[str, object] | None = None) -> ObsRunSummary:
    """End run and derive summary from events.

    `summary` is currently limited to optional terminal metadata:
    - done_reason: str
    """
    record = _RUNS.get(run_id)
    if record is None:
        raise ValueError(f"Unknown run_id '{run_id}'.")
    done_reason = _extract_done_reason(summary)

    finish_event = _create_event(
        context=record.context,
        run_id=record.run_id,
        trace_id=record.trace_id,
        event_type=EVENT_RUN_FINISHED,
        payload={"status": "finished", "done_reason": done_reason},
        redaction_status="not_needed",
        done_reason=done_reason,
    )
    record.events.append(finish_event)
    derived = _derive_run_summary(record.events)
    record.summary = derived

    del _RUNS[run_id]
    _CLOSED_RUNS[run_id] = record
    _prune_retention(record.context.now())
    return derived


def obs_make_event(
    *,
    context: ObsContext,
    run_id: str,
    event_type: str,
    payload: Mapping[str, object],
    redaction_status: RedactionStatus,
    stage_id: str | None = None,
    action_id: str | None = None,
    iteration_id: str | None = None,
    decision_source: str | None = None,
    done_reason: str | None = None,
    policy_version: str | None = None,
    settings_snapshot_id: str | None = None,
    action_input_hash: str | None = None,
    state_before: Mapping[str, object] | None = None,
    state_after: Mapping[str, object] | None = None,
    redaction_version: str | None = None,
) -> ObsEvent:
    if run_id in _RUNS:
        trace_id = _RUNS[run_id].trace_id
    elif run_id in _CLOSED_RUNS:
        trace_id = _CLOSED_RUNS[run_id].trace_id
    else:
        raise ValueError(f"Unknown run_id '{run_id}'.")

    return _create_event(
        context=context,
        run_id=run_id,
        trace_id=trace_id,
        event_type=event_type,
        payload=payload,
        redaction_status=redaction_status,
        stage_id=stage_id,
        action_id=action_id,
        iteration_id=iteration_id,
        decision_source=decision_source,
        done_reason=done_reason,
        policy_version=policy_version,
        settings_snapshot_id=settings_snapshot_id,
        action_input_hash=action_input_hash,
        state_before=state_before,
        state_after=state_after,
        redaction_version=redaction_version,
    )


def obs_get_run_events(run_id: str) -> tuple[ObsEvent, ...]:
    if run_id in _RUNS:
        return tuple(_RUNS[run_id].events)
    if run_id in _CLOSED_RUNS:
        return tuple(_CLOSED_RUNS[run_id].events)
    return tuple()


def obs_get_run_summary(run_id: str) -> ObsRunSummary | None:
    record = _CLOSED_RUNS.get(run_id)
    if record is None:
        return None
    return record.summary


def obs_reset_state() -> None:
    global _RUN_COUNTER
    global _EVENT_COUNTER
    global _TRACE_COUNTER
    _RUNS.clear()
    _CLOSED_RUNS.clear()
    _RUN_COUNTER = count(1)
    _EVENT_COUNTER = count(1)
    _TRACE_COUNTER = count(1)


__all__ = [
    "DEFAULT_RETENTION_SECONDS",
    "EVENT_CATALOG_VERSION",
    "EVENT_RUN_STARTED",
    "EVENT_RUN_FINISHED",
    "EVENT_STAGE_STARTED",
    "EVENT_STAGE_FINISHED",
    "EVENT_STAGE_FAILED",
    "EVENT_ACTION_PLANNED",
    "EVENT_ACTION_EXECUTED",
    "EVENT_ACTION_NOOP",
    "EVENT_ACTION_BLOCKED",
    "EVENT_DECISION_MADE",
    "EVENT_FALLBACK_APPLIED",
    "EVENT_BUDGET_SNAPSHOT",
    "EVENT_BUDGET_EXHAUSTED",
    "EVENT_POLICY_CHECK",
    "EVENT_POLICY_BLOCKED",
    "EVENT_SCHEMA_VERSION",
    "EVENT_TYPES",
    "ObsContext",
    "ObsEvent",
    "ObsRunSummary",
    "obs_end_run",
    "obs_get_run_events",
    "obs_get_run_summary",
    "obs_log_event",
    "obs_make_event",
    "obs_reset_state",
    "obs_start_run",
]

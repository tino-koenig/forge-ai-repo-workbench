"""Canonical step protocol event helpers for capability execution."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


STEP_TYPES = {"deterministic", "llm", "io", "policy"}
STEP_STATUSES = {"started", "completed", "failed", "fallback"}
_MAX_METADATA_DEPTH = 5
_MAX_LIST_ITEMS = 64
_MAX_DICT_ITEMS = 64
_MAX_STRING_LEN = 600
_SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "auth",
    "token",
    "bearer",
    "password",
    "secret",
    "system_prompt",
    "user_prompt",
    "prompt",
}


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_metadata_value(value: Any, *, depth: int = 0) -> Any:
    if depth > _MAX_METADATA_DEPTH:
        return "truncated_depth"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        compact = " ".join(value.strip().split())
        if len(compact) > _MAX_STRING_LEN:
            compact = compact[:_MAX_STRING_LEN].rstrip()
        return compact
    if isinstance(value, list):
        return [
            _sanitize_metadata_value(item, depth=depth + 1)
            for item in value[:_MAX_LIST_ITEMS]
        ]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:_MAX_DICT_ITEMS]:
            key_str = str(key)
            if key_str.lower() in _SENSITIVE_KEYS:
                continue
            out[key_str] = _sanitize_metadata_value(item, depth=depth + 1)
        return out
    return str(value)


def _sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    return _sanitize_metadata_value(metadata, depth=0)


def build_step_event(
    *,
    run_id: int,
    capability: str,
    step_name: str,
    step_type: str,
    status: str,
    duration_ms: int | None = None,
    metadata: dict[str, Any] | None = None,
    timestamp: str | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    normalized_type = step_type if step_type in STEP_TYPES else "deterministic"
    normalized_status = status if status in STEP_STATUSES else "failed"
    normalized_duration = duration_ms
    if normalized_status in {"completed", "failed", "fallback"}:
        if normalized_duration is None:
            normalized_duration = 0
        if normalized_duration < 0:
            normalized_duration = 0

    event: dict[str, Any] = {
        "event_id": event_id or f"evt_{uuid4().hex}",
        "run_id": int(run_id),
        "timestamp": timestamp or _iso_utc_now(),
        "capability": capability,
        "step_name": step_name.strip() or "unknown_step",
        "step_type": normalized_type,
        "status": normalized_status,
        "metadata": _sanitize_metadata(metadata),
    }
    if normalized_duration is not None and normalized_status in {"completed", "failed", "fallback"}:
        event["duration_ms"] = int(normalized_duration)
    return event


def llm_step_events_from_usage(
    *,
    run_id: int,
    capability: str,
    step_name: str,
    usage: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(usage, dict):
        return []
    attempted = bool(usage.get("attempted"))
    used = bool(usage.get("used"))
    fallback_reason = usage.get("fallback_reason")
    if not attempted and not used:
        return []
    latency = usage.get("latency_ms")
    duration_ms = int(latency) if isinstance(latency, int) and latency >= 0 else 0
    status = "completed" if used else "fallback"
    metadata = {
        "provider": usage.get("provider"),
        "model": usage.get("model"),
        "prompt_template": usage.get("prompt_template"),
        "prompt_profile": usage.get("prompt_profile"),
        "mode": usage.get("mode"),
        "policy": usage.get("policy"),
        "token_usage": usage.get("token_usage"),
        "cost_tracking": usage.get("cost_tracking"),
        "cost": usage.get("cost"),
        "fallback_reason": fallback_reason,
    }
    return [
        build_step_event(
            run_id=run_id,
            capability=capability,
            step_name=step_name,
            step_type="llm",
            status="started",
            metadata=metadata,
        ),
        build_step_event(
            run_id=run_id,
            capability=capability,
            step_name=step_name,
            step_type="llm",
            status=status,
            duration_ms=duration_ms,
            metadata=metadata,
        ),
    ]


def normalize_protocol_events(
    *,
    run_id: int,
    capability: str,
    events: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in events:
        if not isinstance(item, dict):
            continue
        normalized.append(
            build_step_event(
                run_id=run_id,
                capability=str(item.get("capability") or capability),
                step_name=str(item.get("step_name") or "unknown_step"),
                step_type=str(item.get("step_type") or "deterministic"),
                status=str(item.get("status") or "failed"),
                duration_ms=item.get("duration_ms") if isinstance(item.get("duration_ms"), int) else None,
                metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
                timestamp=str(item.get("timestamp") or _iso_utc_now()),
                event_id=str(item.get("event_id")) if isinstance(item.get("event_id"), str) else None,
            )
        )
    return normalized

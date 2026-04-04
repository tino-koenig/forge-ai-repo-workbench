"""Protocol event JSONL storage with bounded retention/rotation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import tomli


DEFAULT_MAX_FILE_SIZE_BYTES = 5_000_000
DEFAULT_MAX_EVENT_AGE_DAYS = 30
DEFAULT_MAX_EVENTS_COUNT = 50_000


@dataclass(frozen=True)
class ProtocolLogConfig:
    max_file_size_bytes: int
    max_event_age_days: int
    max_events_count: int


def events_log_path(repo_root: Path) -> Path:
    return repo_root / ".forge" / "logs" / "events.jsonl"


def _safe_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed


def _read_protocol_log_config(repo_root: Path) -> ProtocolLogConfig:
    path = repo_root / ".forge" / "config.toml"
    if not path.exists():
        return ProtocolLogConfig(
            max_file_size_bytes=DEFAULT_MAX_FILE_SIZE_BYTES,
            max_event_age_days=DEFAULT_MAX_EVENT_AGE_DAYS,
            max_events_count=DEFAULT_MAX_EVENTS_COUNT,
        )
    try:
        payload = tomli.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomli.TOMLDecodeError):
        return ProtocolLogConfig(
            max_file_size_bytes=DEFAULT_MAX_FILE_SIZE_BYTES,
            max_event_age_days=DEFAULT_MAX_EVENT_AGE_DAYS,
            max_events_count=DEFAULT_MAX_EVENTS_COUNT,
        )

    logs = payload.get("logs") if isinstance(payload, dict) else None
    protocol = logs.get("protocol") if isinstance(logs, dict) else None
    if not isinstance(protocol, dict):
        return ProtocolLogConfig(
            max_file_size_bytes=DEFAULT_MAX_FILE_SIZE_BYTES,
            max_event_age_days=DEFAULT_MAX_EVENT_AGE_DAYS,
            max_events_count=DEFAULT_MAX_EVENTS_COUNT,
        )

    max_file_size_bytes = _safe_int(protocol.get("max_file_size_bytes"), DEFAULT_MAX_FILE_SIZE_BYTES)
    max_event_age_days = _safe_int(protocol.get("max_event_age_days"), DEFAULT_MAX_EVENT_AGE_DAYS)
    max_events_count = _safe_int(protocol.get("max_events_count"), DEFAULT_MAX_EVENTS_COUNT)

    if max_file_size_bytes < 1024:
        max_file_size_bytes = 1024
    if max_event_age_days < 1:
        max_event_age_days = 1
    if max_events_count < 100:
        max_events_count = 100

    return ProtocolLogConfig(
        max_file_size_bytes=max_file_size_bytes,
        max_event_age_days=max_event_age_days,
        max_events_count=max_events_count,
    )


def _parse_event_line(raw: str) -> dict[str, object] | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _parse_iso_utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _event_is_fresh(event: dict[str, object], cutoff: datetime) -> bool:
    parsed_ts = _parse_iso_utc(event.get("timestamp"))
    if parsed_ts is None:
        return True
    return parsed_ts >= cutoff


def _serialize_event(event: dict[str, object]) -> str:
    return json.dumps(event, ensure_ascii=False, sort_keys=True)


def _rewrite_with_retention(path: Path, config: ProtocolLogConfig) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    events: list[dict[str, object]] = []
    for raw in lines:
        parsed = _parse_event_line(raw)
        if parsed is not None:
            events.append(parsed)

    cutoff = datetime.now(timezone.utc) - timedelta(days=config.max_event_age_days)
    events = [event for event in events if _event_is_fresh(event, cutoff)]
    if len(events) > config.max_events_count:
        events = events[-config.max_events_count :]

    serialized = [_serialize_event(event) for event in events]
    payload = ("\n".join(serialized) + ("\n" if serialized else ""))
    path.write_text(payload, encoding="utf-8")
    return serialized


def _rotate_if_needed(path: Path, *, serialized: list[str], max_file_size_bytes: int) -> None:
    total_bytes = sum(len(line.encode("utf-8")) + 1 for line in serialized)
    if total_bytes <= max_file_size_bytes:
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = path.parent / f"events-{timestamp}.jsonl"
    if path.exists():
        path.replace(archive)

    retained = list(serialized)
    while retained and sum(len(line.encode("utf-8")) + 1 for line in retained) > max_file_size_bytes:
        if len(retained) == 1:
            break
        retained.pop(0)
    payload = ("\n".join(retained) + ("\n" if retained else ""))
    path.write_text(payload, encoding="utf-8")


def append_protocol_events(repo_root: Path, events: list[dict[str, object]]) -> str | None:
    if not events:
        return None
    path = events_log_path(repo_root)
    config = _read_protocol_log_config(repo_root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for event in events:
                fh.write(_serialize_event(event))
                fh.write("\n")
        serialized = _rewrite_with_retention(path, config)
        _rotate_if_needed(path, serialized=serialized, max_file_size_bytes=config.max_file_size_bytes)
    except OSError as exc:
        return f"protocol log write failed: {exc}"
    return None

"""Protocol event JSONL storage with bounded retention/rotation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

import tomli


DEFAULT_MAX_FILE_SIZE_BYTES = 5_000_000
DEFAULT_MAX_EVENT_AGE_DAYS = 30
DEFAULT_MAX_EVENTS_COUNT = 50_000
DEFAULT_MAX_TEXT_LEN = 600

_SENSITIVE_KEY_FRAGMENTS = (
    "api_key",
    "authorization",
    "auth",
    "token",
    "secret",
    "password",
    "bearer",
)
_PROMPT_KEY_FRAGMENTS = ("prompt", "system_message", "user_message")
_ALLOWLIST_PROMPT_KEYS = ("prompt_template", "prompt_profile")
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._\-+/=]+\b", re.IGNORECASE)
_AUTH_RE = re.compile(r"\bAuthorization\s*:\s*[^\s,;]+", re.IGNORECASE)
_OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")


@dataclass(frozen=True)
class ProtocolLogConfig:
    max_file_size_bytes: int
    max_event_age_days: int
    max_events_count: int
    allow_full_prompt_until: datetime | None


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
            allow_full_prompt_until=None,
        )
    try:
        payload = tomli.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomli.TOMLDecodeError):
        return ProtocolLogConfig(
            max_file_size_bytes=DEFAULT_MAX_FILE_SIZE_BYTES,
            max_event_age_days=DEFAULT_MAX_EVENT_AGE_DAYS,
            max_events_count=DEFAULT_MAX_EVENTS_COUNT,
            allow_full_prompt_until=None,
        )

    logs = payload.get("logs") if isinstance(payload, dict) else None
    protocol = logs.get("protocol") if isinstance(logs, dict) else None
    if not isinstance(protocol, dict):
        return ProtocolLogConfig(
            max_file_size_bytes=DEFAULT_MAX_FILE_SIZE_BYTES,
            max_event_age_days=DEFAULT_MAX_EVENT_AGE_DAYS,
            max_events_count=DEFAULT_MAX_EVENTS_COUNT,
            allow_full_prompt_until=None,
        )

    max_file_size_bytes = _safe_int(protocol.get("max_file_size_bytes"), DEFAULT_MAX_FILE_SIZE_BYTES)
    max_event_age_days = _safe_int(protocol.get("max_event_age_days"), DEFAULT_MAX_EVENT_AGE_DAYS)
    max_events_count = _safe_int(protocol.get("max_events_count"), DEFAULT_MAX_EVENTS_COUNT)
    allow_full_prompt_until_raw = protocol.get("allow_full_prompt_until")

    if max_file_size_bytes < 1024:
        max_file_size_bytes = 1024
    if max_event_age_days < 1:
        max_event_age_days = 1
    if max_events_count < 100:
        max_events_count = 100

    allow_full_prompt_until = _parse_iso_utc(allow_full_prompt_until_raw)
    return ProtocolLogConfig(
        max_file_size_bytes=max_file_size_bytes,
        max_event_age_days=max_event_age_days,
        max_events_count=max_events_count,
        allow_full_prompt_until=allow_full_prompt_until,
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


def load_protocol_events(repo_root: Path) -> list[dict[str, object]]:
    path = events_log_path(repo_root)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    events: list[dict[str, object]] = []
    for raw in lines:
        parsed = _parse_event_line(raw)
        if parsed is not None:
            events.append(parsed)
    return events


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


def _collect_known_secret_values() -> list[str]:
    values: list[str] = []
    for key, value in os.environ.items():
        key_lower = key.lower()
        if not any(fragment in key_lower for fragment in _SENSITIVE_KEY_FRAGMENTS):
            continue
        cleaned = value.strip()
        if len(cleaned) < 8:
            continue
        values.append(cleaned)
    # Keep longest secrets first to avoid partial replacement leaks.
    values = sorted(set(values), key=len, reverse=True)
    return values


def _redact_string(value: str, known_secrets: list[str]) -> str:
    redacted = value
    for secret in known_secrets:
        if secret and secret in redacted:
            redacted = redacted.replace(secret, "[redacted_secret]")
    redacted = _BEARER_RE.sub("Bearer [redacted]", redacted)
    redacted = _AUTH_RE.sub("Authorization:[redacted]", redacted)
    redacted = _OPENAI_KEY_RE.sub("[redacted_api_key]", redacted)
    compact = " ".join(redacted.split())
    if len(compact) > DEFAULT_MAX_TEXT_LEN:
        compact = compact[:DEFAULT_MAX_TEXT_LEN].rstrip()
    return compact


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _is_prompt_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _ALLOWLIST_PROMPT_KEYS:
        return False
    return any(fragment in lowered for fragment in _PROMPT_KEY_FRAGMENTS)


def _hash_text(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def _redact_value(
    value: Any,
    *,
    key_hint: str | None,
    known_secrets: list[str],
    allow_full_prompt: bool,
) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if key_hint and _is_prompt_key(key_hint):
            if allow_full_prompt:
                return _redact_string(value, known_secrets)
            return {
                "redacted": True,
                "hash": _hash_text(value),
                "length": len(value),
            }
        if key_hint and _is_sensitive_key(key_hint):
            return "[redacted]"
        return _redact_string(value, known_secrets)
    if isinstance(value, list):
        return [
            _redact_value(item, key_hint=key_hint, known_secrets=known_secrets, allow_full_prompt=allow_full_prompt)
            for item in value
        ]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if _is_sensitive_key(key):
                out[key] = "[redacted]"
                continue
            out[key] = _redact_value(
                item,
                key_hint=key,
                known_secrets=known_secrets,
                allow_full_prompt=allow_full_prompt,
            )
        return out
    return _redact_string(str(value), known_secrets)


def _redact_event(event: dict[str, object], config: ProtocolLogConfig, known_secrets: list[str]) -> dict[str, object]:
    allow_full_prompt = (
        config.allow_full_prompt_until is not None and datetime.now(timezone.utc) <= config.allow_full_prompt_until
    )
    redacted = _redact_value(event, key_hint=None, known_secrets=known_secrets, allow_full_prompt=allow_full_prompt)
    if not isinstance(redacted, dict):
        return {
            "event_id": "evt_redaction_fallback",
            "run_id": event.get("run_id"),
            "timestamp": event.get("timestamp"),
            "capability": event.get("capability"),
            "step_name": "redaction_fallback",
            "step_type": "policy",
            "status": "fallback",
            "metadata": {"warning": "event redaction produced non-dict output"},
        }
    if allow_full_prompt:
        metadata = redacted.get("metadata")
        if isinstance(metadata, dict):
            metadata["redaction_warning"] = (
                "allow_full_prompt_until is active; prompt content may be present temporarily"
            )
    return redacted


def _rewrite_with_retention(path: Path, config: ProtocolLogConfig) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    known_secrets = _collect_known_secret_values()
    events: list[dict[str, object]] = []
    for raw in lines:
        parsed = _parse_event_line(raw)
        if parsed is not None:
            try:
                events.append(_redact_event(parsed, config, known_secrets))
            except Exception:
                events.append(
                    {
                        "event_id": "evt_redaction_error",
                        "run_id": parsed.get("run_id"),
                        "timestamp": parsed.get("timestamp"),
                        "capability": parsed.get("capability"),
                        "step_name": "redaction_error",
                        "step_type": "policy",
                        "status": "fallback",
                        "metadata": {"warning": "event replaced due to redaction failure"},
                    }
                )

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
    known_secrets = _collect_known_secret_values()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for event in events:
                try:
                    safe_event = _redact_event(event, config, known_secrets)
                except Exception as exc:
                    safe_event = {
                        "event_id": "evt_redaction_error",
                        "run_id": event.get("run_id"),
                        "timestamp": event.get("timestamp"),
                        "capability": event.get("capability"),
                        "step_name": "redaction_error",
                        "step_type": "policy",
                        "status": "fallback",
                        "metadata": {"warning": f"event replaced due to redaction failure: {exc}"},
                    }
                fh.write(_serialize_event(safe_event))
                fh.write("\n")
        serialized = _rewrite_with_retention(path, config)
        _rotate_if_needed(path, serialized=serialized, max_file_size_bytes=config.max_file_size_bytes)
    except OSError as exc:
        return f"protocol log write failed: {exc}"
    return None

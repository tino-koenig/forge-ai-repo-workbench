"""Named session persistence with TTL and bounded context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any


SESSION_VERSION = 1
DEFAULT_TTL_MINUTES = 60
MAX_RECENT_CAPABILITIES = 20
MAX_RECENT_QUESTIONS = 20
MAX_QUESTION_CHARS = 160


@dataclass(frozen=True)
class SessionRecord:
    name: str
    created_at: str
    last_activity_at: str
    expires_at: str
    ttl_minutes: int
    runtime_settings: dict[str, object]
    context: dict[str, object]
    meta: dict[str, object]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _session_root(repo_root: Path) -> Path:
    return repo_root / ".forge" / "sessions"


def _index_path(repo_root: Path) -> Path:
    return _session_root(repo_root) / "index.json"


def _session_path(repo_root: Path, name: str) -> Path:
    return _session_root(repo_root) / f"{name}.json"


def _safe_name(name: str) -> str | None:
    candidate = name.strip()
    if not candidate:
        return None
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", candidate):
        return None
    return candidate


def _load_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _empty_index() -> dict[str, object]:
    return {
        "version": SESSION_VERSION,
        "active_session": None,
        "sessions": {},
    }


def _load_index(repo_root: Path) -> dict[str, object]:
    payload = _load_json(_index_path(repo_root))
    if payload is None:
        return _empty_index()
    sessions = payload.get("sessions")
    if not isinstance(sessions, dict):
        payload["sessions"] = {}
    if "active_session" not in payload:
        payload["active_session"] = None
    if "version" not in payload:
        payload["version"] = SESSION_VERSION
    return payload


def _save_index(repo_root: Path, payload: dict[str, object]) -> None:
    payload["version"] = SESSION_VERSION
    _write_json(_index_path(repo_root), payload)


def _default_context() -> dict[str, object]:
    return {
        "recent_capabilities": [],
        "recent_question_summaries": [],
        "active_framework_profile_hint": None,
        "preferences": {},
    }


def _normalize_session_payload(raw: dict[str, object]) -> SessionRecord | None:
    name = raw.get("name")
    created_at = raw.get("created_at")
    last_activity_at = raw.get("last_activity_at")
    expires_at = raw.get("expires_at")
    ttl_minutes = raw.get("ttl_minutes")
    runtime_settings = raw.get("runtime_settings")
    context = raw.get("context")
    meta = raw.get("meta")
    if not isinstance(name, str):
        return None
    if not isinstance(created_at, str) or not isinstance(last_activity_at, str) or not isinstance(expires_at, str):
        return None
    if not isinstance(ttl_minutes, int):
        ttl_minutes = DEFAULT_TTL_MINUTES
    if ttl_minutes < 1 or ttl_minutes > 24 * 60:
        ttl_minutes = DEFAULT_TTL_MINUTES
    if not isinstance(runtime_settings, dict):
        runtime_settings = {}
    if not isinstance(context, dict):
        context = _default_context()
    if not isinstance(meta, dict):
        meta = {"version": SESSION_VERSION}
    return SessionRecord(
        name=name,
        created_at=created_at,
        last_activity_at=last_activity_at,
        expires_at=expires_at,
        ttl_minutes=ttl_minutes,
        runtime_settings={str(k): v for k, v in runtime_settings.items() if isinstance(k, str)},
        context=context,
        meta=meta,
    )


def _to_payload(session: SessionRecord) -> dict[str, object]:
    return {
        "version": SESSION_VERSION,
        "name": session.name,
        "created_at": session.created_at,
        "last_activity_at": session.last_activity_at,
        "expires_at": session.expires_at,
        "ttl_minutes": session.ttl_minutes,
        "runtime_settings": session.runtime_settings,
        "context": session.context,
        "meta": session.meta,
    }


def _session_index_meta(session: SessionRecord) -> dict[str, object]:
    return {
        "name": session.name,
        "created_at": session.created_at,
        "last_activity_at": session.last_activity_at,
        "expires_at": session.expires_at,
        "ttl_minutes": session.ttl_minutes,
        "path": f"{session.name}.json",
    }


def _is_expired(session: SessionRecord, now: datetime) -> bool:
    expires_at = _parse_iso(session.expires_at)
    if expires_at is None:
        return True
    return now > expires_at


def _expires_at(now: datetime, ttl_minutes: int) -> str:
    return _to_iso(now + timedelta(minutes=ttl_minutes))


def _refresh_activity(session: SessionRecord, now: datetime | None = None) -> SessionRecord:
    current = now or _utc_now()
    return SessionRecord(
        name=session.name,
        created_at=session.created_at,
        last_activity_at=_to_iso(current),
        expires_at=_expires_at(current, session.ttl_minutes),
        ttl_minutes=session.ttl_minutes,
        runtime_settings=session.runtime_settings,
        context=session.context,
        meta=session.meta,
    )


def _load_session(repo_root: Path, name: str) -> SessionRecord | None:
    payload = _load_json(_session_path(repo_root, name))
    if payload is None:
        return None
    return _normalize_session_payload(payload)


def _save_session(repo_root: Path, session: SessionRecord) -> None:
    _write_json(_session_path(repo_root, session.name), _to_payload(session))


def _register_session(repo_root: Path, session: SessionRecord, *, activate: bool) -> None:
    index_payload = _load_index(repo_root)
    sessions = index_payload.get("sessions")
    if not isinstance(sessions, dict):
        sessions = {}
        index_payload["sessions"] = sessions
    sessions[session.name] = _session_index_meta(session)
    if activate:
        index_payload["active_session"] = session.name
    _save_index(repo_root, index_payload)


def session_summary(repo_root: Path, name: str) -> dict[str, object] | None:
    payload = _load_session(repo_root, name)
    if payload is None:
        return None
    now = _utc_now()
    return {
        "name": payload.name,
        "created_at": payload.created_at,
        "last_activity_at": payload.last_activity_at,
        "expires_at": payload.expires_at,
        "ttl_minutes": payload.ttl_minutes,
        "expired": _is_expired(payload, now),
        "runtime_settings_keys": sorted(payload.runtime_settings.keys()),
        "context_keys": sorted(payload.context.keys()) if isinstance(payload.context, dict) else [],
        "meta": payload.meta,
    }


def list_sessions(repo_root: Path) -> list[dict[str, object]]:
    now = _utc_now()
    index_payload = _load_index(repo_root)
    active = index_payload.get("active_session")
    sessions_meta = index_payload.get("sessions")
    out: list[dict[str, object]] = []
    if not isinstance(sessions_meta, dict):
        return out
    for name in sorted(sessions_meta.keys()):
        loaded = _load_session(repo_root, name)
        if loaded is None:
            continue
        out.append(
            {
                "name": name,
                "active": isinstance(active, str) and active == name,
                "created_at": loaded.created_at,
                "last_activity_at": loaded.last_activity_at,
                "expires_at": loaded.expires_at,
                "ttl_minutes": loaded.ttl_minutes,
                "expired": _is_expired(loaded, now),
            }
        )
    return out


def create_session(
    repo_root: Path,
    *,
    name: str,
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
    auto_created: bool = False,
    activate: bool = True,
) -> SessionRecord:
    safe = _safe_name(name)
    if safe is None:
        raise ValueError("invalid session name; allowed: [A-Za-z0-9._-], max length 64")
    existing = _load_session(repo_root, safe)
    if existing is not None:
        raise ValueError(f"session '{safe}' already exists")
    now = _utc_now()
    ttl = ttl_minutes if 1 <= ttl_minutes <= 24 * 60 else DEFAULT_TTL_MINUTES
    session = SessionRecord(
        name=safe,
        created_at=_to_iso(now),
        last_activity_at=_to_iso(now),
        expires_at=_expires_at(now, ttl),
        ttl_minutes=ttl,
        runtime_settings={},
        context=_default_context(),
        meta={"version": SESSION_VERSION, "auto_created": auto_created},
    )
    _save_session(repo_root, session)
    _register_session(repo_root, session, activate=activate)
    return session


def _auto_session_name(now: datetime) -> str:
    return now.strftime("auto-%Y%m%d-%H%M%S")


def ensure_active_session(repo_root: Path) -> tuple[SessionRecord, bool, list[str]]:
    warnings: list[str] = []
    now = _utc_now()
    index_payload = _load_index(repo_root)
    active = index_payload.get("active_session")
    if isinstance(active, str):
        loaded = _load_session(repo_root, active)
        if loaded is not None and not _is_expired(loaded, now):
            return loaded, False, warnings
        if loaded is None:
            warnings.append(f"active session '{active}' missing; creating auto session")
        else:
            warnings.append(f"active session '{active}' expired; creating auto session")
    base_name = _auto_session_name(now)
    candidate = base_name
    counter = 2
    while _load_session(repo_root, candidate) is not None:
        candidate = f"{base_name}-{counter}"
        counter += 1
    created = create_session(
        repo_root,
        name=candidate,
        ttl_minutes=DEFAULT_TTL_MINUTES,
        auto_created=True,
        activate=True,
    )
    return created, True, warnings


def get_active_session(repo_root: Path) -> tuple[SessionRecord | None, list[str]]:
    warnings: list[str] = []
    index_payload = _load_index(repo_root)
    active = index_payload.get("active_session")
    if not isinstance(active, str):
        return None, warnings
    loaded = _load_session(repo_root, active)
    if loaded is None:
        warnings.append(f"active session '{active}' missing")
        return None, warnings
    if _is_expired(loaded, _utc_now()):
        warnings.append(f"active session '{active}' expired")
        return None, warnings
    return loaded, warnings


def use_session(repo_root: Path, name: str, *, revive: bool = False) -> tuple[SessionRecord, bool]:
    safe = _safe_name(name)
    if safe is None:
        raise ValueError("invalid session name")
    loaded = _load_session(repo_root, safe)
    if loaded is None:
        raise ValueError(f"session '{safe}' not found")
    now = _utc_now()
    expired = _is_expired(loaded, now)
    if expired and not revive:
        raise ValueError(f"session '{safe}' is expired; use --revive to reactivate")
    revived = False
    if expired:
        revived = True
    refreshed = _refresh_activity(loaded, now)
    _save_session(repo_root, refreshed)
    _register_session(repo_root, refreshed, activate=True)
    return refreshed, revived


def show_session(repo_root: Path, name: str | None = None) -> dict[str, object] | None:
    if name is None:
        active, _warnings = get_active_session(repo_root)
        if active is None:
            return None
        return _to_payload(active)
    safe = _safe_name(name)
    if safe is None:
        return None
    loaded = _load_session(repo_root, safe)
    if loaded is None:
        return None
    return _to_payload(loaded)


def clear_session_context(repo_root: Path, name: str | None = None) -> SessionRecord:
    target = name
    if target is None:
        active, _warnings = get_active_session(repo_root)
        if active is None:
            raise ValueError("no active session")
        target = active.name
    safe = _safe_name(str(target))
    if safe is None:
        raise ValueError("invalid session name")
    loaded = _load_session(repo_root, safe)
    if loaded is None:
        raise ValueError(f"session '{safe}' not found")
    refreshed = _refresh_activity(loaded)
    updated = SessionRecord(
        name=refreshed.name,
        created_at=refreshed.created_at,
        last_activity_at=refreshed.last_activity_at,
        expires_at=refreshed.expires_at,
        ttl_minutes=refreshed.ttl_minutes,
        runtime_settings=refreshed.runtime_settings,
        context=_default_context(),
        meta=refreshed.meta,
    )
    _save_session(repo_root, updated)
    _register_session(repo_root, updated, activate=False)
    return updated


def end_session(repo_root: Path, name: str | None = None) -> str:
    index_payload = _load_index(repo_root)
    active = index_payload.get("active_session")
    target = name or (active if isinstance(active, str) else None)
    if not isinstance(target, str):
        raise ValueError("no active session to end")
    safe = _safe_name(target)
    if safe is None:
        raise ValueError("invalid session name")
    path = _session_path(repo_root, safe)
    if path.exists():
        path.unlink()
    sessions = index_payload.get("sessions")
    if isinstance(sessions, dict):
        sessions.pop(safe, None)
    if active == safe:
        index_payload["active_session"] = None
    _save_index(repo_root, index_payload)
    return safe


def update_session_runtime_settings(repo_root: Path, name: str, values: dict[str, object]) -> SessionRecord:
    safe = _safe_name(name)
    if safe is None:
        raise ValueError("invalid session name")
    loaded = _load_session(repo_root, safe)
    if loaded is None:
        raise ValueError(f"session '{safe}' not found")
    refreshed = _refresh_activity(loaded)
    updated = SessionRecord(
        name=refreshed.name,
        created_at=refreshed.created_at,
        last_activity_at=refreshed.last_activity_at,
        expires_at=refreshed.expires_at,
        ttl_minutes=refreshed.ttl_minutes,
        runtime_settings={str(k): v for k, v in values.items() if isinstance(k, str)},
        context=refreshed.context,
        meta=refreshed.meta,
    )
    _save_session(repo_root, updated)
    _register_session(repo_root, updated, activate=False)
    return updated


def record_activity(
    repo_root: Path,
    *,
    capability: str,
    payload: str,
    framework_profile_hint: str | None = None,
) -> SessionRecord | None:
    active, _warnings = get_active_session(repo_root)
    if active is None:
        return None
    now = _utc_now()
    context = dict(active.context) if isinstance(active.context, dict) else _default_context()
    recent_caps = list(context.get("recent_capabilities", [])) if isinstance(context.get("recent_capabilities"), list) else []
    recent_questions = (
        list(context.get("recent_question_summaries", []))
        if isinstance(context.get("recent_question_summaries"), list)
        else []
    )
    recent_caps.append(str(capability))
    if len(recent_caps) > MAX_RECENT_CAPABILITIES:
        recent_caps = recent_caps[-MAX_RECENT_CAPABILITIES:]
    summary = " ".join((payload or "").strip().split())
    if summary:
        if len(summary) > MAX_QUESTION_CHARS:
            summary = summary[:MAX_QUESTION_CHARS].rstrip()
        recent_questions.append(summary)
        if len(recent_questions) > MAX_RECENT_QUESTIONS:
            recent_questions = recent_questions[-MAX_RECENT_QUESTIONS:]
    context["recent_capabilities"] = recent_caps
    context["recent_question_summaries"] = recent_questions
    if framework_profile_hint:
        context["active_framework_profile_hint"] = framework_profile_hint
    preferences = context.get("preferences")
    if not isinstance(preferences, dict):
        preferences = {}
    for key in ("output.format", "output.view", "llm.mode", "execution.profile", "access.web", "access.write"):
        if key in active.runtime_settings:
            preferences[key] = active.runtime_settings[key]
    context["preferences"] = preferences

    updated = SessionRecord(
        name=active.name,
        created_at=active.created_at,
        last_activity_at=_to_iso(now),
        expires_at=_expires_at(now, active.ttl_minutes),
        ttl_minutes=active.ttl_minutes,
        runtime_settings=active.runtime_settings,
        context=context,
        meta=active.meta,
    )
    _save_session(repo_root, updated)
    _register_session(repo_root, updated, activate=True)
    return updated

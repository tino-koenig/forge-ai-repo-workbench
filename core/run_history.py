"""Run history persistence for Forge capability executions."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from core.protocol_log import append_protocol_events
from core.step_protocol import normalize_protocol_events
from core.step_protocol import build_step_event


def history_path(repo_root: Path) -> Path:
    return repo_root / ".forge" / "runs.jsonl"


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def load_runs(repo_root: Path) -> list[dict[str, Any]]:
    path = history_path(repo_root)
    records: list[dict[str, Any]] = []
    for raw in _read_lines(path):
        raw = raw.strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def get_run(repo_root: Path, run_id: int) -> dict[str, Any] | None:
    for record in load_runs(repo_root):
        if int(record.get("id", -1)) == run_id:
            return record
    return None


def last_run(repo_root: Path) -> dict[str, Any] | None:
    records = load_runs(repo_root)
    if not records:
        return None
    return records[-1]


def append_run(
    repo_root: Path,
    *,
    request: dict[str, Any],
    execution: dict[str, Any],
    output: dict[str, Any],
) -> int:
    path = history_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    records = load_runs(repo_root)
    next_id = (int(records[-1].get("id", 0)) + 1) if records else 1
    execution_payload = dict(execution)
    protocol_events = normalize_protocol_events(
        run_id=next_id,
        capability=str(request.get("capability") or "unknown"),
        events=execution_payload.get("protocol_events") if isinstance(execution_payload.get("protocol_events"), list) else [],
    )
    protocol_warning = append_protocol_events(repo_root, protocol_events)
    protocol_event_metadata: dict[str, Any] = {
        "path": ".forge/logs/events.jsonl",
        "event_count": len(protocol_events),
    }
    protocol_event_status = "completed"
    if protocol_warning:
        protocol_event_status = "fallback"
        protocol_event_metadata["warning"] = protocol_warning
        execution_payload["protocol_log_warning"] = protocol_warning
    protocol_persist_event = build_step_event(
        run_id=next_id,
        capability=str(request.get("capability") or "unknown"),
        step_name="protocol_log_persist",
        step_type="io",
        status=protocol_event_status,
        duration_ms=0,
        metadata=protocol_event_metadata,
    )
    protocol_events.append(protocol_persist_event)
    execution_payload["protocol_events"] = protocol_events
    # Best-effort: include persistence outcome event in JSONL stream too.
    append_protocol_events(repo_root, [protocol_persist_event])
    record = {
        "id": next_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request": request,
        "execution": execution_payload,
        "output": output,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True))
        fh.write("\n")
    return next_id

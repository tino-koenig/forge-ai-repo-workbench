from __future__ import annotations

from argparse import Namespace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any

import tomli
from core.capability_model import Capability, CommandRequest, Profile
from core.effects import ExecutionSession
from core.output_contracts import build_contract, emit_contract_json
from core.run_history import get_run, history_path, last_run, load_runs


DEFAULT_KEEP_LAST = 500
DEFAULT_MAX_AGE_DAYS = 90
DEFAULT_MAX_FILE_MB = 20


def _summary_from_record(record: dict[str, Any]) -> str:
    contract = record.get("output", {}).get("contract")
    if isinstance(contract, dict):
        summary = contract.get("summary")
        if isinstance(summary, str) and summary.strip():
            return summary
    text = str(record.get("output", {}).get("text", "")).strip()
    if not text:
        return "No output captured."
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.strip() == "--- Summary ---" and idx + 1 < len(lines):
            candidate = lines[idx + 1].strip()
            if candidate:
                return candidate[:220]
    return lines[0][:220]


def _next_step_from_record(record: dict[str, Any]) -> str | None:
    contract = record.get("output", {}).get("contract")
    if not isinstance(contract, dict):
        return None
    next_step = contract.get("next_step")
    if isinstance(next_step, str) and next_step.strip():
        return next_step
    return None


def _print_record(record: dict[str, Any], view: str) -> None:
    rid = record.get("id")
    ts = record.get("timestamp")
    req = record.get("request", {})
    exe = record.get("execution", {})
    out = record.get("output", {})
    capability = req.get("capability")
    profile = req.get("profile")
    summary = _summary_from_record(record)

    if view == "compact":
        print(f"#{rid} | {capability}:{profile} | {summary}")
        return

    print(f"Run #{rid} | {ts} | {capability}:{profile} | exit={exe.get('exit_code')}")
    print(f"Payload: {req.get('payload')}")
    print(f"Output format: {exe.get('output_format')}")
    print("\n--- Summary ---")
    print(summary)
    next_step = _next_step_from_record(record)
    if next_step:
        print("\n--- Next Step ---")
        print(next_step)
    if view != "full":
        return

    print("\n--- Full Output ---")
    text = str(out.get("text", "")).rstrip()
    print(text if text else "(empty)")
    contract = out.get("contract")
    if isinstance(contract, dict):
        print("\n--- Stored Contract ---")
        print(json.dumps(contract, ensure_ascii=False, indent=2))


def _parse_runs_command(parts: list[str]) -> tuple[str, int | None, str]:
    # Returns: (action, run_id, view)
    # action in {list,last,show,rerun,prune}
    # view in {compact,standard,full}
    if not parts:
        return "list", None, "standard"

    views = {"compact", "standard", "full"}
    first = parts[0].lower()

    if first == "list":
        return "list", None, "standard"

    if first == "last":
        if len(parts) >= 2 and parts[1].lower() in views:
            return "last", None, parts[1].lower()
        return "last", None, "standard"

    if first == "prune":
        return "prune", None, "standard"

    if first == "show":
        if len(parts) < 2:
            raise ValueError("Usage: forge runs show <id> [compact|standard|full]")
        run_id = int(parts[1])
        view = parts[2].lower() if len(parts) >= 3 else "standard"
        if view not in views:
            raise ValueError("View must be one of: compact|standard|full")
        return "show", run_id, view

    if first.isdigit():
        run_id = int(first)
        if len(parts) == 1:
            return "show", run_id, "standard"
        second = parts[1].lower()
        if second == "rerun":
            return "rerun", run_id, "standard"
        if second == "show":
            view = parts[2].lower() if len(parts) >= 3 else "standard"
            if view not in views:
                raise ValueError("View must be one of: compact|standard|full")
            return "show", run_id, view
        if second in views:
            return "show", run_id, second
        raise ValueError("Usage: forge runs <id> [show] [compact|standard|full] or forge runs <id> rerun")

    raise ValueError("Usage: forge runs [list|last|show <id>|<id> show [view]|<id> rerun|prune]")


def _safe_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _read_retention_from_config(repo_root: Path) -> tuple[int, int | None, int]:
    path = repo_root / ".forge" / "config.toml"
    if not path.exists():
        return DEFAULT_KEEP_LAST, DEFAULT_MAX_AGE_DAYS, DEFAULT_MAX_FILE_MB
    try:
        payload = tomli.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomli.TOMLDecodeError):
        return DEFAULT_KEEP_LAST, DEFAULT_MAX_AGE_DAYS, DEFAULT_MAX_FILE_MB
    runs = payload.get("runs")
    retention = runs.get("retention") if isinstance(runs, dict) else None
    if not isinstance(retention, dict):
        return DEFAULT_KEEP_LAST, DEFAULT_MAX_AGE_DAYS, DEFAULT_MAX_FILE_MB

    keep_last = _safe_int(retention.get("keep_last"))
    max_age_days = _safe_int(retention.get("max_age_days"))
    max_file_mb = _safe_int(retention.get("max_file_mb"))

    resolved_keep = keep_last if keep_last is not None and keep_last > 0 else DEFAULT_KEEP_LAST
    resolved_age = max_age_days if max_age_days is not None and max_age_days >= 0 else DEFAULT_MAX_AGE_DAYS
    resolved_file_mb = max_file_mb if max_file_mb is not None and max_file_mb > 0 else DEFAULT_MAX_FILE_MB
    return resolved_keep, resolved_age, resolved_file_mb


def _history_rows(path: Path) -> tuple[list[tuple[dict[str, Any], str]], int]:
    if not path.exists():
        return [], 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return [], 0

    rows: list[tuple[dict[str, Any], str]] = []
    corrupted = 0
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            corrupted += 1
            continue
        if not isinstance(parsed, dict):
            corrupted += 1
            continue
        rows.append((parsed, line))
    return rows, corrupted


def _id_range(ids: list[int]) -> dict[str, int] | None:
    if not ids:
        return None
    return {"min": min(ids), "max": max(ids)}


def _run_prune(request: CommandRequest, args, repo_root: Path, is_json: bool) -> int:
    if args.keep_last is not None and args.keep_last <= 0:
        message = "--keep-last must be > 0"
        if is_json:
            emit_contract_json(
                build_contract(
                    capability=request.capability.value,
                    profile=request.profile.value,
                    summary="Invalid prune arguments.",
                    evidence=[],
                    uncertainty=[message],
                    next_step="Run: forge runs prune --dry-run",
                    sections={"status": "fail"},
                )
            )
            return 1
        print(message)
        return 1
    if args.older_than_days is not None and args.older_than_days < 0:
        message = "--older-than-days must be >= 0"
        if is_json:
            emit_contract_json(
                build_contract(
                    capability=request.capability.value,
                    profile=request.profile.value,
                    summary="Invalid prune arguments.",
                    evidence=[],
                    uncertainty=[message],
                    next_step="Run: forge runs prune --dry-run",
                    sections={"status": "fail"},
                )
            )
            return 1
        print(message)
        return 1

    cfg_keep_last, cfg_max_age_days, cfg_max_file_mb = _read_retention_from_config(repo_root)
    keep_last = args.keep_last if args.keep_last is not None else cfg_keep_last
    older_than_days = args.older_than_days if args.older_than_days is not None else cfg_max_age_days
    max_file_mb = cfg_max_file_mb
    dry_run = bool(args.dry_run)

    path = history_path(repo_root)
    rows, corrupted_count = _history_rows(path)
    valid_records = [row[0] for row in rows]
    before_count = len(valid_records)
    now = datetime.now(timezone.utc)

    kept_rows = list(rows)
    removed_rows: list[tuple[dict[str, Any], str]] = []

    if older_than_days is not None:
        cutoff = now - timedelta(days=older_than_days)
        age_kept: list[tuple[dict[str, Any], str]] = []
        for row in kept_rows:
            record = row[0]
            ts = _parse_timestamp(record.get("timestamp"))
            if ts is not None and ts < cutoff:
                removed_rows.append(row)
            else:
                age_kept.append(row)
        kept_rows = age_kept

    if keep_last is not None and len(kept_rows) > keep_last:
        remove_n = len(kept_rows) - keep_last
        removed_rows.extend(kept_rows[:remove_n])
        kept_rows = kept_rows[remove_n:]

    removed_ids = [rid for rid in (_safe_int(item[0].get("id")) for item in removed_rows) if rid is not None]
    kept_ids = [rid for rid in (_safe_int(item[0].get("id")) for item in kept_rows) if rid is not None]

    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for record, _ in kept_rows:
                fh.write(json.dumps(record, sort_keys=True))
                fh.write("\n")

    after_count = len(kept_rows)
    removed_count = len(removed_rows)
    file_mb = (os.path.getsize(path) / (1024 * 1024)) if path.exists() else 0.0
    max_file_warning = file_mb > max_file_mb

    criteria = {
        "keep_last": keep_last,
        "older_than_days": older_than_days,
        "max_file_mb": max_file_mb,
        "dry_run": dry_run,
    }
    sections = {
        "status": "ok",
        "criteria": criteria,
        "counts": {
            "before_valid": before_count,
            "after_valid": after_count,
            "removed_valid": removed_count,
            "corrupted_skipped": corrupted_count,
        },
        "affected_id_ranges": {
            "removed": _id_range(removed_ids),
            "remaining": _id_range(kept_ids),
        },
        "history_file_mb": round(file_mb, 3),
        "max_file_warning": max_file_warning,
    }
    summary = (
        f"Runs prune {'preview' if dry_run else 'completed'}: "
        f"removed={removed_count}, remaining={after_count}, corrupted_skipped={corrupted_count}."
    )
    uncertainty: list[str] = []
    if corrupted_count > 0:
        uncertainty.append("Corrupted history lines were skipped safely.")
    if max_file_warning:
        uncertainty.append(
            f"History file size {file_mb:.2f} MB exceeds configured max_file_mb={max_file_mb}."
        )
    next_step = "Run: forge runs list"

    if is_json:
        emit_contract_json(
            build_contract(
                capability=request.capability.value,
                profile=request.profile.value,
                summary=summary,
                evidence=[],
                uncertainty=uncertainty,
                next_step=next_step,
                sections=sections,
            )
        )
        return 0

    print("=== FORGE RUNS PRUNE ===")
    print(f"Mode: {'dry-run' if dry_run else 'apply'}")
    print(f"Criteria: keep_last={keep_last}, older_than_days={older_than_days}, max_file_mb={max_file_mb}")
    print(f"Valid runs: before={before_count}, removed={removed_count}, after={after_count}")
    print(f"Corrupted lines skipped: {corrupted_count}")
    print(f"History file size: {file_mb:.2f} MB")
    if removed_ids:
        print(f"Removed id range: {_id_range(removed_ids)['min']}..{_id_range(removed_ids)['max']}")
    if kept_ids:
        print(f"Remaining id range: {_id_range(kept_ids)['min']}..{_id_range(kept_ids)['max']}")
    if max_file_warning:
        print(f"Warning: history file exceeds configured max_file_mb={max_file_mb}")
    if uncertainty:
        print("\n--- Notes ---")
        for item in uncertainty:
            print(f"- {item}")
    return 0


def _rerun_record(
    *,
    record: dict[str, Any],
    current_args: Namespace,
) -> int:
    from core.runtime import execute

    req = record.get("request", {})
    capability = req.get("capability")
    profile = req.get("profile", Profile.STANDARD.value)
    payload = req.get("payload", "")
    if not isinstance(capability, str):
        print("Run record is missing capability; cannot rerun.")
        return 1
    if capability == Capability.RUNS.value:
        print("Refusing to rerun 'runs' command from history.")
        return 1

    replay_request = CommandRequest(
        capability=Capability(capability),
        profile=Profile(profile),
        payload=str(payload),
    )
    replay_args = Namespace(**vars(current_args))
    if hasattr(replay_args, "parts"):
        replay_args.parts = []
    return execute(request=replay_request, args=replay_args)


def run(request: CommandRequest, args, session: ExecutionSession) -> int:
    repo_root = Path(args.repo_root).resolve()
    is_json = args.output_format == "json"
    parts: list[str] = list(getattr(args, "parts", []) or [])

    try:
        action, run_id, view = _parse_runs_command(parts)
    except ValueError as exc:
        if is_json:
            contract = build_contract(
                capability=request.capability.value,
                profile=request.profile.value,
                summary="Invalid runs command.",
                evidence=[],
                uncertainty=[str(exc)],
                next_step="Run: forge runs list",
                sections={"status": "fail"},
            )
            emit_contract_json(contract)
            return 1
        print(str(exc))
        return 1

    if action == "prune":
        return _run_prune(request, args, repo_root, is_json)

    records = load_runs(repo_root)
    if action == "list":
        tail = records[-12:]
        if is_json:
            contract = build_contract(
                capability=request.capability.value,
                profile=request.profile.value,
                summary=f"Runs listed: {len(tail)} entries.",
                evidence=[],
                uncertainty=[],
                next_step="Run: forge runs last",
                sections={
                    "runs": [
                        {
                            "id": item.get("id"),
                            "timestamp": item.get("timestamp"),
                            "capability": item.get("request", {}).get("capability"),
                            "profile": item.get("request", {}).get("profile"),
                            "summary": _summary_from_record(item),
                        }
                        for item in tail
                    ]
                },
            )
            emit_contract_json(contract)
            return 0
        print("=== FORGE RUNS ===")
        if not tail:
            print("No runs recorded.")
            return 0
        for item in tail:
            print(
                f"#{item.get('id')} | {item.get('timestamp')} | "
                f"{item.get('request', {}).get('capability')}:{item.get('request', {}).get('profile')} | "
                f"{_summary_from_record(item)}"
            )
        return 0

    if action == "last":
        record = last_run(repo_root)
        if record is None:
            if is_json:
                contract = build_contract(
                    capability=request.capability.value,
                    profile=request.profile.value,
                    summary="No runs available.",
                    evidence=[],
                    uncertainty=["Run history is empty."],
                    next_step="Execute a capability, then run: forge runs last",
                    sections={"status": "empty"},
                )
                emit_contract_json(contract)
                return 0
            print("No runs recorded.")
            return 0
        if is_json:
            emit_contract_json(record)
            return 0
        _print_record(record, view)
        return 0

    assert run_id is not None
    record = get_run(repo_root, run_id)
    if record is None:
        if is_json:
            contract = build_contract(
                capability=request.capability.value,
                profile=request.profile.value,
                summary=f"Run {run_id} not found.",
                evidence=[],
                uncertainty=[f"No run with id={run_id} in history."],
                next_step="Run: forge runs list",
                sections={"status": "missing"},
            )
            emit_contract_json(contract)
            return 1
        print(f"Run {run_id} not found.")
        return 1

    if action == "show":
        if is_json:
            emit_contract_json(record)
            return 0
        _print_record(record, view)
        return 0

    if action == "rerun":
        if is_json:
            print("Rerun emits execution output; use text output format for interactive use.")
        return _rerun_record(record=record, current_args=args)

    return 1

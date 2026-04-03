from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path
from typing import Any

from core.capability_model import Capability, CommandRequest, Profile
from core.effects import ExecutionSession
from core.output_contracts import build_contract, emit_contract_json
from core.run_history import get_run, last_run, load_runs


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
    # action in {list,last,show,rerun}
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

    raise ValueError("Usage: forge runs [list|last|show <id>|<id> show [view]|<id> rerun]")


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

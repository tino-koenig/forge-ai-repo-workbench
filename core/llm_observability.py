"""Redacted local observability for LLM invocation paths."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core.capability_model import Capability, Profile
from core.config import ResolvedLLMConfig


def _trim_file(path: Path, keep_last: int, max_size_bytes: int) -> None:
    if not path.exists():
        return
    if path.stat().st_size <= max_size_bytes:
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= keep_last:
        tail = lines
    else:
        tail = lines[-keep_last:]
    try:
        path.write_text("\n".join(tail) + ("\n" if tail else ""), encoding="utf-8")
    except OSError:
        return


def log_llm_event(
    *,
    repo_root: Path | None,
    settings: ResolvedLLMConfig,
    capability: Capability,
    profile: Profile,
    stage: str,
    task: str,
    usage: dict[str, object],
    extra: dict[str, object] | None = None,
) -> None:
    if not settings.observability_enabled:
        return
    if repo_root is None:
        return

    logs_dir = repo_root / ".forge" / "logs"
    log_file = logs_dir / "llm_observability.jsonl"
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    level = settings.observability_level
    event: dict[str, object] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "capability": capability.value,
        "profile": profile.value,
        "stage": stage,
        "provider": usage.get("provider"),
        "model": usage.get("model"),
        "base_url": usage.get("base_url"),
        "mode": usage.get("mode"),
        "attempted": usage.get("attempted"),
        "used": usage.get("used"),
        "fallback_reason": usage.get("fallback_reason"),
    }
    if level in {"standard", "debug"}:
        event["prompt_template"] = usage.get("prompt_template")
        event["prompt_profile"] = usage.get("prompt_profile")
        event["system_template"] = usage.get("system_template")
        event["timeout_s"] = settings.timeout_s
        event["context_budget_tokens"] = usage.get("context_budget_tokens")
        event["max_output_tokens"] = usage.get("max_output_tokens")
        event["temperature"] = usage.get("temperature")
        event["config_source"] = usage.get("config_source")
    if level == "debug":
        event["latency_ms"] = usage.get("latency_ms")
        event["task_preview"] = " ".join(task.strip().split())[:160]
        if extra:
            event["extra"] = extra

    # Explicit redaction/safety guards.
    event.pop("api_key", None)
    event.pop("authorization", None)
    event.pop("prompt", None)
    event.pop("user_prompt", None)
    event.pop("system_prompt", None)
    serialized = json.dumps(event, ensure_ascii=False)
    if "Bearer " in serialized or "Authorization" in serialized or "FORGE_LLM_API_KEY=" in serialized:
        return

    try:
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(serialized + "\n")
    except OSError:
        return

    _trim_file(
        log_file,
        keep_last=settings.observability_retention_count,
        max_size_bytes=settings.observability_max_file_mb * 1024 * 1024,
    )

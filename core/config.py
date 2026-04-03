"""Configuration loading and precedence resolution for Forge."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Any

import tomli


ALLOWED_PROMPT_PROFILES = {
    "strict_read_only",
    "review_strict",
    "describe_onboarding",
}


@dataclass(frozen=True)
class ResolvedLLMConfig:
    mode: str
    provider: str | None
    base_url: str | None
    model: str | None
    timeout_s: float
    api_key_env: str
    api_key: str | None
    context_budget_tokens: int
    max_output_tokens: int
    temperature: float
    prompt_profile: str
    system_template_path: Path
    source: dict[str, str]
    validation_error: str | None = None


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return tomli.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomli.TOMLDecodeError) as exc:
        return {"_error": f"invalid TOML config: {exc}"}


def _nested_get(data: dict[str, Any], path: str) -> Any:
    cursor: Any = data
    for part in path.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            return None
        cursor = cursor[part]
    return cursor


def _first_non_none(pairs: list[tuple[str, Any]]) -> tuple[Any, str]:
    for source, value in pairs:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value, source
    return None, "default"


def _float_or_default(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_or_default(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _default_system_template() -> Path:
    return Path(__file__).resolve().parents[1] / "prompts" / "system" / "default_read_only.txt"


def resolve_llm_config(args, repo_root: Path) -> ResolvedLLMConfig:
    config_path = repo_root / ".forge" / "config.toml"
    local_config_path = repo_root / ".forge" / "config.local.toml"
    payload = _load_toml(config_path)
    local_payload = _load_toml(local_config_path)
    if "_error" in payload:
        return ResolvedLLMConfig(
            mode=args.llm_mode,
            provider=None,
            base_url=None,
            model=None,
            timeout_s=30.0,
            api_key_env="FORGE_LLM_API_KEY",
            api_key=None,
            context_budget_tokens=12000,
            max_output_tokens=700,
            temperature=0.2,
            prompt_profile="strict_read_only",
            system_template_path=_default_system_template(),
            source={"config": "error"},
            validation_error=str(payload["_error"]),
        )
    if "_error" in local_payload:
        return ResolvedLLMConfig(
            mode=args.llm_mode,
            provider=None,
            base_url=None,
            model=None,
            timeout_s=30.0,
            api_key_env="FORGE_LLM_API_KEY",
            api_key=None,
            context_budget_tokens=12000,
            max_output_tokens=700,
            temperature=0.2,
            prompt_profile="strict_read_only",
            system_template_path=_default_system_template(),
            source={"config.local": "error"},
            validation_error=str(local_payload["_error"]),
        )

    source: dict[str, str] = {}
    provider, source["provider"] = _first_non_none(
        [
            ("cli", getattr(args, "llm_provider", None)),
            ("env", os.environ.get("FORGE_LLM_PROVIDER")),
            ("toml_local", _nested_get(local_payload, "llm.provider")),
            ("toml", _nested_get(payload, "llm.provider")),
        ]
    )
    base_url, source["base_url"] = _first_non_none(
        [
            ("cli", getattr(args, "llm_base_url", None)),
            ("env", os.environ.get("FORGE_LLM_BASE_URL")),
            ("toml_local", _nested_get(local_payload, "llm.openai_compatible.base_url")),
            ("toml", _nested_get(payload, "llm.openai_compatible.base_url")),
        ]
    )
    model, source["model"] = _first_non_none(
        [
            ("cli", getattr(args, "llm_model", None)),
            ("env", os.environ.get("FORGE_LLM_MODEL")),
            ("toml_local", _nested_get(local_payload, "llm.openai_compatible.model")),
            ("toml", _nested_get(payload, "llm.openai_compatible.model")),
        ]
    )

    timeout_raw, source["timeout_s"] = _first_non_none(
        [
            ("cli", getattr(args, "llm_timeout_s", None)),
            ("env", os.environ.get("FORGE_LLM_TIMEOUT_S")),
            ("toml_local", _nested_get(local_payload, "llm.openai_compatible.timeout_s")),
            ("toml", _nested_get(payload, "llm.openai_compatible.timeout_s")),
        ]
    )
    timeout_s = _float_or_default(timeout_raw, 30.0)

    api_key_env_name, source["api_key_env"] = _first_non_none(
        [
            ("env", os.environ.get("FORGE_LLM_API_KEY_ENV")),
            ("toml_local", _nested_get(local_payload, "llm.openai_compatible.api_key_env")),
            ("toml", _nested_get(payload, "llm.openai_compatible.api_key_env")),
            ("default", "FORGE_LLM_API_KEY"),
        ]
    )
    api_key_env = str(api_key_env_name)
    api_key = os.environ.get(api_key_env)

    context_budget_raw, source["context_budget_tokens"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.request.context_budget_tokens")),
            ("toml", _nested_get(payload, "llm.request.context_budget_tokens")),
        ]
    )
    max_output_raw, source["max_output_tokens"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.request.max_output_tokens")),
            ("toml", _nested_get(payload, "llm.request.max_output_tokens")),
        ]
    )
    temperature_raw, source["temperature"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.request.temperature")),
            ("toml", _nested_get(payload, "llm.request.temperature")),
        ]
    )
    context_budget_tokens = _int_or_default(context_budget_raw, 12000)
    max_output_tokens = _int_or_default(max_output_raw, 700)
    temperature = _float_or_default(temperature_raw, 0.2)

    prompt_profile_raw, source["prompt_profile"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.prompt.profile")),
            ("toml", _nested_get(payload, "llm.prompt.profile")),
            ("default", "strict_read_only"),
        ]
    )
    prompt_profile = str(prompt_profile_raw)

    system_template_raw, source["system_template"] = _first_non_none(
        [
            ("toml_local", _nested_get(local_payload, "llm.prompt.system_template")),
            ("toml", _nested_get(payload, "llm.prompt.system_template")),
        ]
    )
    if isinstance(system_template_raw, str) and system_template_raw.strip():
        system_template = Path(system_template_raw.strip())
        system_template_path = (
            system_template if system_template.is_absolute() else (repo_root / system_template).resolve()
        )
    else:
        system_template_path = _default_system_template()

    validation_errors: list[str] = []
    if provider is not None and provider not in {"openai_compatible", "mock"}:
        validation_errors.append(f"unknown provider '{provider}'")
    if timeout_s <= 0:
        validation_errors.append("timeout_s must be > 0")
    if context_budget_tokens <= 0:
        validation_errors.append("context_budget_tokens must be > 0")
    if max_output_tokens <= 0:
        validation_errors.append("max_output_tokens must be > 0")
    if temperature < 0 or temperature > 2:
        validation_errors.append("temperature must be within [0, 2]")
    if prompt_profile not in ALLOWED_PROMPT_PROFILES:
        validation_errors.append(f"unknown prompt profile '{prompt_profile}'")
    if not system_template_path.exists():
        validation_errors.append(f"missing system template: {system_template_path}")
    elif not system_template_path.is_file():
        validation_errors.append(f"system template is not a file: {system_template_path}")
    elif not os.access(system_template_path, os.R_OK):
        validation_errors.append(f"system template not readable: {system_template_path}")

    validation_error = "; ".join(validation_errors) if validation_errors else None

    return ResolvedLLMConfig(
        mode=args.llm_mode,
        provider=str(provider) if isinstance(provider, str) else None,
        base_url=str(base_url) if isinstance(base_url, str) else None,
        model=str(model) if isinstance(model, str) else None,
        timeout_s=timeout_s,
        api_key_env=api_key_env,
        api_key=api_key,
        context_budget_tokens=context_budget_tokens,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        prompt_profile=prompt_profile,
        system_template_path=system_template_path,
        source=source,
        validation_error=validation_error,
    )

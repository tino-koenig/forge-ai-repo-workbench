from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib import error, request

from core.capability_model import CommandRequest
from core.capability_model import Capability
from core.config import resolve_llm_config
from core.effects import ExecutionSession
from core.output_contracts import build_contract, emit_contract_json
from core.prompt_profiles import default_prompt_profile, is_prompt_profile_allowed
from core.output_views import is_compact, is_full, resolve_view
from core.review_rules import load_review_rules


@dataclass
class CheckResult:
    key: str
    status: str  # pass | warn | fail
    detail: str
    recommendation: str | None = None


def _probe_endpoint(base_url: str, api_key: str, timeout_s: float) -> tuple[str, str]:
    if base_url.startswith("mock://"):
        return "pass", "mock endpoint probe simulated"
    endpoint = f"{base_url.rstrip('/')}/models"
    req = request.Request(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        models = payload.get("data", [])
        if isinstance(models, list):
            return "pass", f"endpoint reachable; model count={len(models)}"
        return "pass", "endpoint reachable"
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return "fail", f"http {exc.code}: {detail}"
    except error.URLError as exc:
        return "fail", f"network error: {exc.reason}"
    except json.JSONDecodeError:
        return "warn", "endpoint reachable but response is not valid JSON"


def _overall_status(results: list[CheckResult]) -> str:
    if any(item.status == "fail" for item in results):
        return "fail"
    if any(item.status == "warn" for item in results):
        return "warn"
    return "pass"


def _next_step(overall: str) -> str:
    if overall == "pass":
        return "Run: forge query standard \"where is the main entrypoint\""
    if overall == "warn":
        return "Resolve warnings and re-run: forge doctor --check-llm-endpoint"
    return "Fix failing checks and re-run: forge doctor --check-llm-endpoint"


def run(request: CommandRequest, args, session: ExecutionSession) -> int:
    repo_root = Path(args.repo_root).resolve()
    view = resolve_view(args)
    config = resolve_llm_config(args, repo_root)
    checks: list[CheckResult] = []

    checks.append(
        CheckResult(
            key="repo_root",
            status="pass" if repo_root.exists() and repo_root.is_dir() else "fail",
            detail=f"repo root resolved to {repo_root}",
            recommendation=None if repo_root.exists() and repo_root.is_dir() else "Set --repo-root to a valid directory.",
        )
    )

    config_path = repo_root / ".forge" / "config.toml"
    local_config_path = repo_root / ".forge" / "config.local.toml"
    checks.append(
        CheckResult(
            key="config_toml",
            status="pass" if config_path.exists() else "warn",
            detail=f"{config_path} {'found' if config_path.exists() else 'not found'}",
            recommendation=None if config_path.exists() else "Create .forge/config.toml for versioned team defaults.",
        )
    )
    checks.append(
        CheckResult(
            key="config_local_toml",
            status="pass" if local_config_path.exists() else "warn",
            detail=f"{local_config_path} {'found' if local_config_path.exists() else 'not found'}",
            recommendation=None if local_config_path.exists() else "Use .forge/config.local.toml for local provider/secrets wiring.",
        )
    )

    env_path = Path(args.env_file).resolve() if args.env_file else (repo_root / ".env")
    checks.append(
        CheckResult(
            key="env_file",
            status="pass" if env_path.exists() else "warn",
            detail=f"{env_path} {'found' if env_path.exists() else 'not found'}",
            recommendation=None if env_path.exists() else "Optional: add .env for local secrets (kept out of VCS).",
        )
    )

    if config.validation_error:
        checks.append(
            CheckResult(
                key="config_validation",
                status="fail",
                detail=config.validation_error,
                recommendation="Fix invalid .forge/config.toml or .forge/config.local.toml values.",
            )
        )
    else:
        checks.append(
            CheckResult(
                key="config_validation",
                status="pass",
                detail="config values passed validation",
            )
        )

    loaded_rules, rule_errors = load_review_rules(repo_root)
    if rule_errors:
        checks.append(
            CheckResult(
                key="review_rules",
                status="warn",
                detail=f"loaded={len(loaded_rules)}; invalid={len(rule_errors)}",
                recommendation="Fix .forge/review-rules.toml invalid entries; invalid rules are skipped safely.",
            )
        )
    else:
        checks.append(
            CheckResult(
                key="review_rules",
                status="pass",
                detail=f"loaded={len(loaded_rules)}; invalid=0",
                recommendation=None,
            )
        )

    if config.provider is None:
        checks.append(
            CheckResult(
                key="llm_provider",
                status="warn",
                detail="no LLM provider configured",
                recommendation="Set provider in .forge/config.toml/.forge/config.local.toml or FORGE_LLM_PROVIDER.",
            )
        )
    elif config.provider in {"openai_compatible", "mock"}:
        checks.append(CheckResult(key="llm_provider", status="pass", detail=f"provider={config.provider}"))
    else:
        checks.append(
            CheckResult(
                key="llm_provider",
                status="fail",
                detail=f"unsupported provider {config.provider}",
                recommendation="Use provider=openai_compatible (or mock for local tests).",
            )
        )

    if config.source.get("prompt_profile") == "default":
        checks.append(
            CheckResult(
                key="prompt_profile_mapping",
                status="pass",
                detail="capability-default prompt profile mapping active",
            )
        )
    else:
        selected = config.prompt_profile
        invalid_caps = [
            cap.value
            for cap in (
                Capability.QUERY,
                Capability.EXPLAIN,
                Capability.REVIEW,
                Capability.DESCRIBE,
                Capability.TEST,
            )
            if not is_prompt_profile_allowed(cap, selected)
        ]
        if invalid_caps:
            checks.append(
                CheckResult(
                    key="prompt_profile_mapping",
                    status="fail",
                    detail=f"profile '{selected}' not allowed for capabilities: {', '.join(invalid_caps)}",
                    recommendation="Use capability defaults or a compatible profile for all targeted capabilities.",
                )
            )
        else:
            checks.append(
                CheckResult(
                    key="prompt_profile_mapping",
                    status="pass",
                    detail=f"profile '{selected}' is compatible with core analysis capabilities",
                )
            )

    if config.provider == "openai_compatible":
        checks.append(
            CheckResult(
                key="llm_base_url",
                status="pass" if bool(config.base_url) else "fail",
                detail=f"base_url={config.base_url or 'unset'}",
                recommendation=None if config.base_url else "Set llm.openai_compatible.base_url.",
            )
        )
        checks.append(
            CheckResult(
                key="llm_model",
                status="pass" if bool(config.model) else "fail",
                detail=f"model={config.model or 'unset'}",
                recommendation=None if config.model else "Set llm.openai_compatible.model.",
            )
        )
        checks.append(
            CheckResult(
                key="llm_api_key",
                status="pass" if bool(config.api_key) else "warn",
                detail=f"api key env={config.api_key_env}; {'present' if config.api_key else 'missing'}",
                recommendation=None if config.api_key else f"Set env var {config.api_key_env}.",
            )
        )

        if args.check_llm_endpoint and config.base_url and config.api_key:
            status, detail = _probe_endpoint(config.base_url, config.api_key, config.timeout_s)
            checks.append(
                CheckResult(
                    key="llm_endpoint_probe",
                    status=status,
                    detail=detail,
                    recommendation=None if status == "pass" else "Verify endpoint URL, auth key, and network reachability.",
                )
            )
        elif args.check_llm_endpoint:
            checks.append(
                CheckResult(
                    key="llm_endpoint_probe",
                    status="warn",
                    detail="probe skipped (missing base_url or api_key)",
                    recommendation="Set base_url and API key, then retry endpoint probe.",
                )
            )

    obs_status = "pass" if config.observability_enabled else "warn"
    checks.append(
        CheckResult(
            key="llm_observability",
            status=obs_status,
            detail=(
                f"enabled={config.observability_enabled}; level={config.observability_level}; "
                f"retention_count={config.observability_retention_count}; max_file_mb={config.observability_max_file_mb}"
            ),
            recommendation=(
                None
                if config.observability_enabled
                else "Optional: enable [llm.observability] in .forge/config.toml for local diagnostics logging."
            ),
        )
    )

    overall = _overall_status(checks)
    uncertainty = [
        "Doctor checks are point-in-time and environment-dependent.",
    ]
    summary = f"Doctor status: {overall}. checks={len(checks)}"
    next_step = _next_step(overall)

    if args.output_format == "json":
        contract = build_contract(
            capability=request.capability.value,
            profile=request.profile.value,
            summary=summary,
            evidence=[],
            uncertainty=uncertainty,
            next_step=next_step,
            sections={
                "status": overall,
                "checks": [
                    {
                        "key": item.key,
                        "status": item.status,
                        "detail": item.detail,
                        "recommendation": item.recommendation,
                    }
                    for item in checks
                ],
                "review_rules": {"loaded": len(loaded_rules), "errors": rule_errors},
            },
        )
        emit_contract_json(contract)
        return 0

    print("=== FORGE DOCTOR ===")
    print(f"Profile: {request.profile.value}")
    print(f"Repo root: {repo_root}")
    print("\n--- Summary ---")
    print(summary)
    print("\n--- Checks ---")
    visible_checks = checks
    if is_compact(view):
        visible_checks = [item for item in checks if item.status in {"fail", "warn"}][:6]
    elif not is_full(view):
        visible_checks = checks[:8]
    for item in visible_checks:
        print(f"- [{item.status}] {item.key}: {item.detail}")
        if item.recommendation and not is_compact(view):
            print(f"  Recommendation: {item.recommendation}")
    print("\n--- Uncertainty ---")
    notes = uncertainty if is_full(view) else uncertainty[:1]
    for note in notes:
        print(f"- {note}")
    print("\n--- Next Step ---")
    print(next_step)
    return 0

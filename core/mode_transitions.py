"""Explicit mode-transition policy and gate evaluation for from-run workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomli


TRANSITION_POLICY_GRAPH: dict[str, frozenset[str]] = {
    "query": frozenset({"explain", "review", "describe", "test"}),
    "explain": frozenset({"review", "describe", "test"}),
    "review": frozenset({"explain", "describe", "test"}),
    "describe": frozenset({"explain", "review", "test"}),
    "test": frozenset({"explain", "review", "describe", "fix"}),
    "fix": frozenset({"review", "test"}),
}

SEVERITY_SCORE = {"low": 1, "medium": 2, "high": 3}
VALID_THRESHOLDS = frozenset({"none", "low", "medium", "high"})


@dataclass(frozen=True)
class TransitionGateDecision:
    gate: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"gate": self.gate, "status": self.status, "detail": self.detail}


@dataclass(frozen=True)
class TransitionPolicyConfig:
    require_confirmation: bool
    review_to_test_min_severity: str
    test_to_fix_require_failure: bool
    source: dict[str, str]


@dataclass(frozen=True)
class TransitionEvaluation:
    allowed: bool
    reason: str
    gate_decisions: list[TransitionGateDecision]
    policy: dict[str, object]


def validate_transition_graph() -> list[str]:
    errors: list[str] = []
    for source, targets in TRANSITION_POLICY_GRAPH.items():
        if not source or not source.islower():
            errors.append(f"invalid source mode '{source}'")
        for target in targets:
            if not target or not target.islower():
                errors.append(f"invalid target mode '{source}->{target}'")
    return errors


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return tomli.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomli.TOMLDecodeError):
        return {}


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
        return value, source
    return None, "default"


def _bool_or_default(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _normalize_threshold(value: Any) -> str:
    if value is None:
        return "low"
    candidate = str(value).strip().lower()
    if candidate in VALID_THRESHOLDS:
        return candidate
    return "low"


def load_transition_policy_config(repo_root: Path) -> TransitionPolicyConfig:
    config_path = repo_root / ".forge" / "config.toml"
    local_path = repo_root / ".forge" / "config.local.toml"
    payload = _load_toml(config_path)
    local = _load_toml(local_path)
    source: dict[str, str] = {}

    require_confirmation_raw, source["require_confirmation"] = _first_non_none(
        [
            ("toml_local", _nested_get(local, "transitions.require_confirmation")),
            ("toml", _nested_get(payload, "transitions.require_confirmation")),
            ("default", False),
        ]
    )
    review_to_test_raw, source["review_to_test_min_severity"] = _first_non_none(
        [
            ("toml_local", _nested_get(local, "transitions.gates.review_to_test_min_severity")),
            ("toml", _nested_get(payload, "transitions.gates.review_to_test_min_severity")),
            ("default", "low"),
        ]
    )
    test_to_fix_raw, source["test_to_fix_require_failure"] = _first_non_none(
        [
            ("toml_local", _nested_get(local, "transitions.gates.test_to_fix_require_failure")),
            ("toml", _nested_get(payload, "transitions.gates.test_to_fix_require_failure")),
            ("default", True),
        ]
    )
    return TransitionPolicyConfig(
        require_confirmation=_bool_or_default(require_confirmation_raw, False),
        review_to_test_min_severity=_normalize_threshold(review_to_test_raw),
        test_to_fix_require_failure=_bool_or_default(test_to_fix_raw, True),
        source=source,
    )


def _extract_findings_severities(source_record: dict[str, Any]) -> list[str]:
    contract = source_record.get("output", {}).get("contract")
    if not isinstance(contract, dict):
        return []
    sections = contract.get("sections", {})
    if not isinstance(sections, dict):
        return []
    findings = sections.get("findings")
    if not isinstance(findings, list):
        return []
    severities: list[str] = []
    for item in findings:
        if not isinstance(item, dict):
            continue
        value = str(item.get("severity", "")).strip().lower()
        if value in SEVERITY_SCORE:
            severities.append(value)
    return severities


def _has_test_failures(source_record: dict[str, Any]) -> bool:
    contract = source_record.get("output", {}).get("contract")
    if not isinstance(contract, dict):
        return False
    sections = contract.get("sections", {})
    if not isinstance(sections, dict):
        return False
    failing_tests = sections.get("failing_tests")
    if isinstance(failing_tests, list) and len(failing_tests) > 0:
        return True
    status = str(sections.get("status", "")).strip().lower()
    return status in {"fail", "failed", "error"}


def evaluate_mode_transition(
    *,
    repo_root: Path,
    source_mode: str,
    target_mode: str,
    source_record: dict[str, Any],
    explicit_confirmation: bool,
) -> TransitionEvaluation:
    decisions: list[TransitionGateDecision] = []
    graph_errors = validate_transition_graph()
    if graph_errors:
        decisions.append(
            TransitionGateDecision(
                gate="graph_valid",
                status="fail",
                detail="; ".join(graph_errors[:3]),
            )
        )
        return TransitionEvaluation(
            allowed=False,
            reason="invalid_transition_graph",
            gate_decisions=decisions,
            policy={"graph_declared": False},
        )

    allowed_targets = TRANSITION_POLICY_GRAPH.get(source_mode, frozenset())
    if target_mode not in allowed_targets:
        decisions.append(
            TransitionGateDecision(
                gate="graph_declared",
                status="fail",
                detail=f"transition {source_mode}->{target_mode} is not declared",
            )
        )
        return TransitionEvaluation(
            allowed=False,
            reason="transition_not_declared",
            gate_decisions=decisions,
            policy={"graph_declared": True},
        )

    decisions.append(
        TransitionGateDecision(
            gate="graph_declared",
            status="pass",
            detail=f"transition {source_mode}->{target_mode} is declared",
        )
    )

    cfg = load_transition_policy_config(repo_root)
    if cfg.require_confirmation:
        if explicit_confirmation:
            decisions.append(
                TransitionGateDecision(
                    gate="confirmation",
                    status="pass",
                    detail="explicit transition confirmation provided",
                )
            )
        else:
            decisions.append(
                TransitionGateDecision(
                    gate="confirmation",
                    status="fail",
                    detail="transition confirmation is required by policy",
                )
            )
            return TransitionEvaluation(
                allowed=False,
                reason="confirmation_required",
                gate_decisions=decisions,
                policy={
                    "graph_declared": True,
                    "require_confirmation": cfg.require_confirmation,
                    "review_to_test_min_severity": cfg.review_to_test_min_severity,
                    "test_to_fix_require_failure": cfg.test_to_fix_require_failure,
                    "config_source": cfg.source,
                },
            )
    else:
        decisions.append(
            TransitionGateDecision(
                gate="confirmation",
                status="skipped",
                detail="transition confirmation not required by policy",
            )
        )

    if source_mode == "review" and target_mode == "test":
        threshold = cfg.review_to_test_min_severity
        if threshold == "none":
            decisions.append(
                TransitionGateDecision(
                    gate="review_findings_threshold",
                    status="skipped",
                    detail="severity threshold disabled",
                )
            )
        else:
            findings = _extract_findings_severities(source_record)
            threshold_score = SEVERITY_SCORE[threshold]
            max_score = max((SEVERITY_SCORE.get(item, 0) for item in findings), default=0)
            if max_score >= threshold_score:
                decisions.append(
                    TransitionGateDecision(
                        gate="review_findings_threshold",
                        status="pass",
                        detail=f"max finding severity satisfies threshold >= {threshold}",
                    )
                )
            else:
                decisions.append(
                    TransitionGateDecision(
                        gate="review_findings_threshold",
                        status="fail",
                        detail=f"review findings do not satisfy threshold >= {threshold}",
                    )
                )
                return TransitionEvaluation(
                    allowed=False,
                    reason="review_findings_threshold_not_met",
                    gate_decisions=decisions,
                    policy={
                        "graph_declared": True,
                        "require_confirmation": cfg.require_confirmation,
                        "review_to_test_min_severity": cfg.review_to_test_min_severity,
                        "test_to_fix_require_failure": cfg.test_to_fix_require_failure,
                        "config_source": cfg.source,
                    },
                )
    else:
        decisions.append(
            TransitionGateDecision(
                gate="review_findings_threshold",
                status="skipped",
                detail="gate applies only to review->test",
            )
        )

    if source_mode == "test" and target_mode == "fix":
        if cfg.test_to_fix_require_failure:
            if _has_test_failures(source_record):
                decisions.append(
                    TransitionGateDecision(
                        gate="test_failure_presence",
                        status="pass",
                        detail="test failures detected",
                    )
                )
            else:
                decisions.append(
                    TransitionGateDecision(
                        gate="test_failure_presence",
                        status="fail",
                        detail="no test failures detected for test->fix transition",
                    )
                )
                return TransitionEvaluation(
                    allowed=False,
                    reason="test_failure_required",
                    gate_decisions=decisions,
                    policy={
                        "graph_declared": True,
                        "require_confirmation": cfg.require_confirmation,
                        "review_to_test_min_severity": cfg.review_to_test_min_severity,
                        "test_to_fix_require_failure": cfg.test_to_fix_require_failure,
                        "config_source": cfg.source,
                    },
                )
        else:
            decisions.append(
                TransitionGateDecision(
                    gate="test_failure_presence",
                    status="skipped",
                    detail="test failure gate disabled",
                )
            )
    else:
        decisions.append(
            TransitionGateDecision(
                gate="test_failure_presence",
                status="skipped",
                detail="gate applies only to test->fix",
            )
        )

    return TransitionEvaluation(
        allowed=True,
        reason="transition_allowed",
        gate_decisions=decisions,
        policy={
            "graph_declared": True,
            "require_confirmation": cfg.require_confirmation,
            "review_to_test_min_severity": cfg.review_to_test_min_severity,
            "test_to_fix_require_failure": cfg.test_to_fix_require_failure,
            "config_source": cfg.source,
        },
    )

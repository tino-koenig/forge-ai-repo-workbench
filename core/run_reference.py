"""Deterministic run-history reference resolution for capability inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.capability_model import Capability
from core.mode_transitions import evaluate_mode_transition
from core.run_history import get_run


class RunReferenceError(ValueError):
    """Raised when a --from-run reference cannot be resolved safely."""


def _extract_query_payload(contract: dict[str, Any]) -> tuple[str | None, str]:
    sections = contract.get("sections", {})
    if not isinstance(sections, dict):
        return None, "query contract sections missing"
    likely = sections.get("likely_locations")
    if not isinstance(likely, list) or not likely:
        return None, "query run has no likely_locations"
    first = likely[0]
    if not isinstance(first, dict):
        return None, "query run likely_locations entry malformed"
    path = first.get("path")
    if not isinstance(path, str) or not path.strip():
        return None, "query run likely_locations[0].path missing"
    return path.strip(), "query_top_likely_location"


def _extract_review_payload(contract: dict[str, Any]) -> tuple[str | None, str]:
    sections = contract.get("sections", {})
    if not isinstance(sections, dict):
        return None, "review contract sections missing"
    findings = sections.get("findings")
    if not isinstance(findings, list) or not findings:
        return None, "review run has no findings"
    first_finding = findings[0]
    if not isinstance(first_finding, dict):
        return None, "review run first finding malformed"
    evidence = first_finding.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return None, "review run first finding has no evidence"
    first_evidence = evidence[0]
    if not isinstance(first_evidence, dict):
        return None, "review run first evidence malformed"
    path = first_evidence.get("path")
    if not isinstance(path, str) or not path.strip():
        return None, "review run first evidence path missing"
    return path.strip(), "review_top_finding_evidence_path"


def _extract_describe_or_test_payload(contract: dict[str, Any], source_capability: str) -> tuple[str | None, str]:
    sections = contract.get("sections", {})
    if not isinstance(sections, dict):
        return None, f"{source_capability} contract sections missing"
    resolved_target = sections.get("resolved_target")
    if isinstance(resolved_target, dict):
        path = resolved_target.get("path")
        if isinstance(path, str) and path.strip():
            return path.strip(), f"{source_capability}_resolved_target_path"
        return None, f"{source_capability} run resolved_target.path missing"
    if isinstance(resolved_target, str) and resolved_target.strip():
        return resolved_target.strip(), f"{source_capability}_resolved_target"
    return None, f"{source_capability} run has no resolved_target"


def resolve_from_run_payload(
    *,
    repo_root: Path,
    requested_capability: Capability,
    explicit_payload: str,
    from_run_id: int | None,
    confirm_transition: bool = False,
) -> tuple[str, dict[str, object] | None]:
    if from_run_id is None:
        return explicit_payload, None
    if explicit_payload.strip():
        raise RunReferenceError(
            "Do not combine direct target/question with --from-run. "
            "Use either explicit payload or --from-run <id>."
        )

    record = get_run(repo_root, int(from_run_id))
    if record is None:
        raise RunReferenceError(
            f"Run {from_run_id} not found. "
            f"Check available IDs with: forge runs list"
        )

    request = record.get("request", {})
    source_capability = request.get("capability")
    if not isinstance(source_capability, str):
        raise RunReferenceError(
            f"Run {from_run_id} is malformed: missing request.capability. "
            f"Inspect with: forge runs {from_run_id} show full"
        )

    if source_capability not in {"query", "review", "describe", "test", "fix"}:
        raise RunReferenceError(
            f"Run {from_run_id} capability '{source_capability}' is not supported for --from-run. "
            f"Supported source runs: query, review, describe, test, fix. "
            f"Inspect with: forge runs {from_run_id} show full"
        )

    output = record.get("output", {})
    contract = output.get("contract")
    if not isinstance(contract, dict):
        raise RunReferenceError(
            f"Run {from_run_id} has no structured contract output. "
            f"This is a legacy/text-only run record. Re-run the source capability to persist a contract, "
            f"then retry --from-run. Inspect with: forge runs {from_run_id} show full"
        )

    transition = evaluate_mode_transition(
        repo_root=repo_root,
        source_mode=source_capability,
        target_mode=requested_capability.value,
        source_record=record,
        explicit_confirmation=bool(confirm_transition),
    )
    if not transition.allowed:
        gate_details = ", ".join(
            f"{item.gate}:{item.status}"
            for item in transition.gate_decisions
            if item.status == "fail"
        )
        base = (
            f"Transition {source_capability}->{requested_capability.value} blocked by policy "
            f"({transition.reason})."
        )
        if gate_details:
            base = f"{base} Failing gates: {gate_details}."
        if transition.reason == "confirmation_required":
            base = (
                f"{base} Re-run with --confirm-transition to allow explicitly "
                f"(if this transition is intended)."
            )
        raise RunReferenceError(base)

    resolved_payload: str | None
    strategy: str
    if source_capability == "query":
        resolved_payload, strategy = _extract_query_payload(contract)
    elif source_capability == "review":
        resolved_payload, strategy = _extract_review_payload(contract)
    else:
        resolved_payload, strategy = _extract_describe_or_test_payload(contract, source_capability)

    if not resolved_payload:
        raise RunReferenceError(
            f"Run {from_run_id} could not be resolved to a target payload ({strategy}). "
            f"Inspect with: forge runs {from_run_id} show full"
        )

    metadata: dict[str, object] = {
        "source_run_id": int(from_run_id),
        "source_run_capability": source_capability,
        "resolved_from_run_strategy": strategy,
        "resolved_from_run_payload": resolved_payload,
        "resolved_for_capability": requested_capability.value,
        "transition_source_mode": source_capability,
        "transition_target_mode": requested_capability.value,
        "transition_reason": "from_run_reference",
        "transition_policy_reason": transition.reason,
        "transition_gate_decisions": [item.to_dict() for item in transition.gate_decisions],
        "transition_policy": transition.policy,
    }
    return resolved_payload, metadata

"""Output Contract Foundation (10): JSON-first contract builder and view derivation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, Sequence

ContractSeverity = Literal["info", "warning", "error"]
SectionStatus = Literal["available", "not_applicable", "omitted", "fallback"]

CONTRACT_VERSION = "10.1"

REQUIRED_SECTION_KEYS: tuple[str, ...] = (
    "action_orchestration",
    "budget",
    "llm_usage",
    "provenance",
    "diagnostics",
    "limits",
    "runtime_settings",
    "policy_violations",
)

SUPPORTED_VIEWS: tuple[str, ...] = ("compact", "standard", "full")
NORMATIVE_DECISION_VALUES: tuple[str, ...] = ("continue", "stop")
NORMATIVE_CONTROL_SIGNALS: tuple[str, ...] = ("none", "replan", "recover", "handoff", "block")
NORMATIVE_DONE_REASONS: tuple[str, ...] = ("sufficient_evidence", "no_progress", "budget_exhausted", "policy_blocked", "error")


@dataclass(frozen=True)
class ContractDiagnostic:
    code: str
    message: str
    severity: ContractSeverity
    section: str | None = None


@dataclass(frozen=True)
class SectionInput:
    payload: Mapping[str, object] | None = None
    status_hint: SectionStatus | None = None
    fallback_reason: str | None = None


@dataclass(frozen=True)
class SectionBuilderResult:
    section_name: str
    payload: Mapping[str, object]
    status: SectionStatus
    diagnostics: tuple[ContractDiagnostic, ...]
    section_version: str

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "section_version": self.section_version,
            "payload": dict(self.payload),
            "diagnostics": [
                {
                    "code": item.code,
                    "message": item.message,
                    "severity": item.severity,
                    "section": item.section,
                }
                for item in self.diagnostics
            ],
        }


@dataclass(frozen=True)
class OutputContract:
    capability: str
    profile: str
    summary: str
    evidence: tuple[Mapping[str, object], ...]
    uncertainty: tuple[str, ...]
    next_step: str
    sections: Mapping[str, SectionBuilderResult]
    contract_version: str = CONTRACT_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "capability": self.capability,
            "profile": self.profile,
            "summary": self.summary,
            "evidence": [dict(item) for item in self.evidence],
            "uncertainty": list(self.uncertainty),
            "next_step": self.next_step,
            "sections": {key: value.as_dict() for key, value in self.sections.items()},
        }


class SectionBuilderBase:
    section_name: str
    section_version: str
    allowed_payload_keys: tuple[str, ...]

    def __init__(self, section_name: str, section_version: str, allowed_payload_keys: tuple[str, ...]) -> None:
        self.section_name = section_name
        self.section_version = section_version
        self.allowed_payload_keys = allowed_payload_keys

    def build(self, section_input: SectionInput | None) -> SectionBuilderResult:
        diagnostics: list[ContractDiagnostic] = []

        if section_input is None:
            section_input = SectionInput()

        status = self._resolve_status(section_input)
        payload = dict(section_input.payload or {})

        sanitized: dict[str, object] = {}
        for key, value in payload.items():
            if key in self.allowed_payload_keys:
                sanitized[key] = value
            else:
                diagnostics.append(
                    ContractDiagnostic(
                        code="unknown_section_field",
                        message=f"Field '{key}' is not part of section schema.",
                        severity="warning",
                        section=self.section_name,
                    )
                )

        if status == "fallback" and section_input.fallback_reason:
            sanitized.setdefault("fallback_reason", section_input.fallback_reason)

        return SectionBuilderResult(
            section_name=self.section_name,
            payload=sanitized,
            status=status,
            diagnostics=tuple(diagnostics),
            section_version=self.section_version,
        )

    @staticmethod
    def _resolve_status(section_input: SectionInput) -> SectionStatus:
        if section_input.status_hint is not None:
            return section_input.status_hint
        if section_input.fallback_reason:
            return "fallback"
        if section_input.payload is None:
            return "not_applicable"
        if len(section_input.payload) == 0:
            return "omitted"
        return "available"


_SECTION_BUILDERS: dict[str, SectionBuilderBase] = {
    "action_orchestration": SectionBuilderBase(
        "action_orchestration",
        "1",
        ("status", "done_reason", "actions", "iterations", "metadata"),
    ),
    "budget": SectionBuilderBase(
        "budget",
        "1",
        ("limits", "usage", "remaining", "exhausted", "snapshots"),
    ),
    "llm_usage": SectionBuilderBase(
        "llm_usage",
        "1",
        ("used", "attempted", "provider", "model", "token_usage", "cost", "stage_usage"),
    ),
    "provenance": SectionBuilderBase(
        "provenance",
        "1",
        ("sources", "evidence_source", "retrieval", "resolver", "ranking"),
    ),
    "diagnostics": SectionBuilderBase(
        "diagnostics",
        "1",
        ("items",),
    ),
    "limits": SectionBuilderBase(
        "limits",
        "1",
        ("items", "limits", "usage", "remaining", "exhausted"),
    ),
    "runtime_settings": SectionBuilderBase(
        "runtime_settings",
        "1",
        ("values", "sources", "diagnostics"),
    ),
    "policy_violations": SectionBuilderBase(
        "policy_violations",
        "1",
        ("items",),
    ),
}


def build_contract_core(
    *,
    capability: str,
    profile: str,
    summary: str,
    evidence: Sequence[Mapping[str, object]],
    uncertainty: Sequence[str],
    next_step: str,
    section_inputs: Mapping[str, SectionInput] | None = None,
    contract_version: str = CONTRACT_VERSION,
) -> OutputContract:
    inputs = dict(section_inputs or {})
    unknown_section_keys = sorted(set(inputs.keys()) - set(REQUIRED_SECTION_KEYS))
    if unknown_section_keys:
        unknown_joined = ", ".join(unknown_section_keys)
        raise ValueError(f"Unknown section_inputs keys: {unknown_joined}")

    sections: dict[str, SectionBuilderResult] = {}
    for section_key in REQUIRED_SECTION_KEYS:
        builder = _SECTION_BUILDERS[section_key]
        sections[section_key] = builder.build(inputs.get(section_key))

    return OutputContract(
        capability=capability,
        profile=profile,
        summary=summary,
        evidence=tuple(dict(item) for item in evidence),
        uncertainty=tuple(str(item) for item in uncertainty),
        next_step=next_step,
        sections=sections,
        contract_version=contract_version,
    )


def validate_contract_schema(contract: OutputContract | Mapping[str, object]) -> list[ContractDiagnostic]:
    payload = contract.as_dict() if isinstance(contract, OutputContract) else dict(contract)
    diagnostics: list[ContractDiagnostic] = []

    required_top = ("contract_version", "capability", "profile", "summary", "evidence", "uncertainty", "next_step", "sections")
    for key in required_top:
        if key not in payload:
            diagnostics.append(
                ContractDiagnostic(
                    code="missing_contract_field",
                    message=f"Missing required contract field '{key}'.",
                    severity="error",
                )
            )

    sections = payload.get("sections")
    if not isinstance(sections, Mapping):
        diagnostics.append(
            ContractDiagnostic(
                code="invalid_sections_mapping",
                message="sections must be a mapping.",
                severity="error",
            )
        )
        return diagnostics

    for section_key in REQUIRED_SECTION_KEYS:
        if section_key not in sections:
            diagnostics.append(
                ContractDiagnostic(
                    code="missing_required_section",
                    message=f"Missing required section '{section_key}'.",
                    severity="error",
                    section=section_key,
                )
            )
            continue

        section_payload = sections[section_key]
        if not isinstance(section_payload, Mapping):
            diagnostics.append(
                ContractDiagnostic(
                    code="invalid_section_shape",
                    message=f"Section '{section_key}' must be a mapping.",
                    severity="error",
                    section=section_key,
                )
            )
            continue

        status = section_payload.get("status")
        if status not in ("available", "not_applicable", "omitted", "fallback"):
            diagnostics.append(
                ContractDiagnostic(
                    code="invalid_section_status",
                    message=f"Section '{section_key}' has invalid status '{status}'.",
                    severity="error",
                    section=section_key,
                )
            )

    _validate_core_section_semantics(sections, diagnostics)

    # Keep diagnostics/policy_violations/limits semantically separate.
    diag_payload = sections.get("diagnostics", {})
    policy_payload = sections.get("policy_violations", {})
    limits_payload = sections.get("limits", {})

    if isinstance(diag_payload, Mapping) and isinstance(policy_payload, Mapping):
        diag_items = diag_payload.get("payload", {}).get("items") if isinstance(diag_payload.get("payload"), Mapping) else None
        policy_items = policy_payload.get("payload", {}).get("items") if isinstance(policy_payload.get("payload"), Mapping) else None
        if diag_items is policy_items and diag_items is not None:
            diagnostics.append(
                ContractDiagnostic(
                    code="section_semantic_overlap",
                    message="diagnostics and policy_violations must not share the same items object.",
                    severity="error",
                )
            )

    if isinstance(limits_payload, Mapping):
        limits_data = limits_payload.get("payload")
        if not isinstance(limits_data, Mapping):
            diagnostics.append(
                ContractDiagnostic(
                    code="invalid_limits_payload",
                    message="limits payload must be a mapping.",
                    severity="error",
                    section="limits",
                )
            )

    return diagnostics


def _validate_core_section_semantics(
    sections: Mapping[str, object], diagnostics: list[ContractDiagnostic]
) -> None:
    orchestration = sections.get("action_orchestration")
    if isinstance(orchestration, Mapping):
        _validate_action_orchestration_semantics(orchestration, diagnostics)

    budget = sections.get("budget")
    if isinstance(budget, Mapping):
        _validate_budget_semantics(budget, diagnostics)

    runtime_settings = sections.get("runtime_settings")
    if isinstance(runtime_settings, Mapping):
        _validate_runtime_settings_semantics(runtime_settings, diagnostics)

    diagnostics_section = sections.get("diagnostics")
    if isinstance(diagnostics_section, Mapping):
        _validate_items_payload_semantics(diagnostics_section, diagnostics, "diagnostics")

    policy_violations = sections.get("policy_violations")
    if isinstance(policy_violations, Mapping):
        _validate_items_payload_semantics(policy_violations, diagnostics, "policy_violations")

    limits = sections.get("limits")
    if isinstance(limits, Mapping):
        _validate_limits_semantics(limits, diagnostics)


def _validate_action_orchestration_semantics(
    section_payload: Mapping[str, object], diagnostics: list[ContractDiagnostic]
) -> None:
    payload = section_payload.get("payload")
    status = section_payload.get("status")
    if status in ("available", "fallback") and not isinstance(payload, Mapping):
        diagnostics.append(
            ContractDiagnostic(
                code="invalid_action_orchestration_payload",
                message="action_orchestration payload must be a mapping when section is available or fallback.",
                severity="error",
                section="action_orchestration",
            )
        )
        return
    if not isinstance(payload, Mapping):
        return

    if "status" in payload and not isinstance(payload["status"], str):
        diagnostics.append(
            ContractDiagnostic(
                code="invalid_action_orchestration_status",
                message="action_orchestration.payload.status must be a string.",
                severity="error",
                section="action_orchestration",
            )
        )
    if "done_reason" in payload and not isinstance(payload["done_reason"], str):
        diagnostics.append(
            ContractDiagnostic(
                code="invalid_action_orchestration_done_reason",
                message="action_orchestration.payload.done_reason must be a string.",
                severity="error",
                section="action_orchestration",
            )
        )
    decision = payload.get("decision")
    if "decision" in payload and not isinstance(decision, str):
        diagnostics.append(
            ContractDiagnostic(
                code="invalid_action_orchestration_decision",
                message="action_orchestration.payload.decision must be a string.",
                severity="error",
                section="action_orchestration",
            )
        )
    if isinstance(decision, str) and decision not in NORMATIVE_DECISION_VALUES:
        diagnostics.append(
            ContractDiagnostic(
                code="invalid_action_orchestration_decision_value",
                message=(
                    "action_orchestration.payload.decision must be one of: "
                    f"{', '.join(NORMATIVE_DECISION_VALUES)}."
                ),
                severity="error",
                section="action_orchestration",
            )
        )
    control_signal = payload.get("control_signal")
    if "control_signal" in payload and not isinstance(control_signal, str):
        diagnostics.append(
            ContractDiagnostic(
                code="invalid_action_orchestration_control_signal_type",
                message="action_orchestration.payload.control_signal must be a string.",
                severity="error",
                section="action_orchestration",
            )
        )
    if isinstance(control_signal, str) and control_signal not in NORMATIVE_CONTROL_SIGNALS:
        diagnostics.append(
            ContractDiagnostic(
                code="invalid_action_orchestration_control_signal",
                message=(
                    "action_orchestration.payload.control_signal must be one of: "
                    f"{', '.join(NORMATIVE_CONTROL_SIGNALS)}."
                ),
                severity="error",
                section="action_orchestration",
            )
        )
    done_reason = payload.get("done_reason")
    if isinstance(done_reason, str) and done_reason not in NORMATIVE_DONE_REASONS:
        diagnostics.append(
            ContractDiagnostic(
                code="invalid_action_orchestration_done_reason_value",
                message=(
                    "action_orchestration.payload.done_reason must be one of: "
                    f"{', '.join(NORMATIVE_DONE_REASONS)}."
                ),
                severity="error",
                section="action_orchestration",
            )
        )


def _validate_budget_semantics(section_payload: Mapping[str, object], diagnostics: list[ContractDiagnostic]) -> None:
    payload = section_payload.get("payload")
    status = section_payload.get("status")
    if status in ("available", "fallback") and not isinstance(payload, Mapping):
        diagnostics.append(
            ContractDiagnostic(
                code="invalid_budget_payload",
                message="budget payload must be a mapping when section is available or fallback.",
                severity="error",
                section="budget",
            )
        )
        return
    if not isinstance(payload, Mapping):
        return

    expected_keys = ("limits", "usage", "remaining", "exhausted", "snapshots")
    if status in ("available", "fallback") and not any(key in payload for key in expected_keys):
        diagnostics.append(
            ContractDiagnostic(
                code="budget_minimum_semantics_missing",
                message="budget payload should include at least one budget semantic key.",
                severity="error",
                section="budget",
            )
        )


def _validate_runtime_settings_semantics(
    section_payload: Mapping[str, object], diagnostics: list[ContractDiagnostic]
) -> None:
    payload = section_payload.get("payload")
    status = section_payload.get("status")
    if status in ("available", "fallback") and not isinstance(payload, Mapping):
        diagnostics.append(
            ContractDiagnostic(
                code="invalid_runtime_settings_payload",
                message="runtime_settings payload must be a mapping when section is available or fallback.",
                severity="error",
                section="runtime_settings",
            )
        )
        return
    if not isinstance(payload, Mapping):
        return

    values = payload.get("values")
    if status in ("available", "fallback") and not isinstance(values, Mapping):
        diagnostics.append(
            ContractDiagnostic(
                code="runtime_settings_values_required",
                message="runtime_settings.payload.values must be a mapping for available or fallback status.",
                severity="error",
                section="runtime_settings",
            )
        )


def _validate_items_payload_semantics(
    section_payload: Mapping[str, object], diagnostics: list[ContractDiagnostic], section_name: str
) -> None:
    payload = section_payload.get("payload")
    status = section_payload.get("status")
    if status in ("available", "fallback") and not isinstance(payload, Mapping):
        diagnostics.append(
            ContractDiagnostic(
                code=f"invalid_{section_name}_payload",
                message=f"{section_name} payload must be a mapping when section is available or fallback.",
                severity="error",
                section=section_name,
            )
        )
        return
    if not isinstance(payload, Mapping):
        return

    items = payload.get("items")
    if status in ("available", "fallback") and not isinstance(items, list):
        diagnostics.append(
            ContractDiagnostic(
                code=f"{section_name}_items_required",
                message=f"{section_name}.payload.items must be a list for available or fallback status.",
                severity="error",
                section=section_name,
            )
        )


def _validate_limits_semantics(section_payload: Mapping[str, object], diagnostics: list[ContractDiagnostic]) -> None:
    payload = section_payload.get("payload")
    status = section_payload.get("status")
    if status in ("available", "fallback") and not isinstance(payload, Mapping):
        diagnostics.append(
            ContractDiagnostic(
                code="invalid_limits_payload",
                message="limits payload must be a mapping when section is available or fallback.",
                severity="error",
                section="limits",
            )
        )
        return
    if not isinstance(payload, Mapping):
        return

    expected_keys = ("items", "limits", "usage", "remaining", "exhausted")
    if status in ("available", "fallback") and not any(key in payload for key in expected_keys):
        diagnostics.append(
            ContractDiagnostic(
                code="limits_minimum_semantics_missing",
                message="limits payload should include at least one limits semantic key.",
                severity="error",
                section="limits",
            )
        )


def render_view(contract: OutputContract | Mapping[str, object], view: str = "standard") -> str:
    payload = contract.as_dict() if isinstance(contract, OutputContract) else dict(contract)

    if view not in SUPPORTED_VIEWS:
        raise ValueError(f"Unsupported view '{view}'. Expected one of: {', '.join(SUPPORTED_VIEWS)}")

    lines: list[str] = []
    lines.append(f"Capability: {payload.get('capability', '')}")
    lines.append(f"Profile: {payload.get('profile', '')}")
    lines.append(f"Summary: {payload.get('summary', '')}")

    if view == "compact":
        pass
    elif view in ("standard", "full"):
        next_step = payload.get("next_step", "")
        lines.append(f"Next Step: {next_step}")

    if view == "full":
        evidence = payload.get("evidence", [])
        uncertainty = payload.get("uncertainty", [])
        lines.append(f"Evidence Count: {len(evidence) if isinstance(evidence, list) else 0}")
        lines.append(f"Uncertainty Count: {len(uncertainty) if isinstance(uncertainty, list) else 0}")

    sections = payload.get("sections", {})
    if isinstance(sections, Mapping):
        lines.append("Sections:")
        for section_key in REQUIRED_SECTION_KEYS:
            section = sections.get(section_key)
            status = "missing"
            if isinstance(section, Mapping):
                status = str(section.get("status", "missing"))
            lines.append(f"- {section_key}: {status}")

        if view == "full":
            orchestration = sections.get("action_orchestration")
            if isinstance(orchestration, Mapping):
                orch_payload = orchestration.get("payload")
                if isinstance(orch_payload, Mapping):
                    if "status" in orch_payload:
                        lines.append(f"Action Status: {orch_payload['status']}")
                    if "done_reason" in orch_payload:
                        lines.append(f"Done Reason: {orch_payload['done_reason']}")

    return "\n".join(lines)


__all__ = [
    "CONTRACT_VERSION",
    "ContractDiagnostic",
    "OutputContract",
    "REQUIRED_SECTION_KEYS",
    "SectionBuilderResult",
    "SectionInput",
    "SUPPORTED_VIEWS",
    "build_contract_core",
    "render_view",
    "validate_contract_schema",
]

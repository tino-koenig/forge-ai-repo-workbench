from __future__ import annotations

import unittest

from core.output_contract_foundation import (
    CONTRACT_VERSION,
    REQUIRED_SECTION_KEYS,
    SectionInput,
    build_contract_core,
    render_view,
    validate_contract_schema,
)


class OutputContractFoundationTests(unittest.TestCase):
    def test_sections_are_stable_mapping_with_required_keys(self) -> None:
        contract = build_contract_core(
            capability="query",
            profile="standard",
            summary="ok",
            evidence=({"id": 1},),
            uncertainty=("none",),
            next_step="next",
            section_inputs={},
        )
        self.assertEqual(tuple(contract.sections.keys()), REQUIRED_SECTION_KEYS)

    def test_section_status_semantics(self) -> None:
        contract = build_contract_core(
            capability="query",
            profile="standard",
            summary="ok",
            evidence=(),
            uncertainty=(),
            next_step="next",
            section_inputs={
                "budget": SectionInput(payload={}),
                "llm_usage": SectionInput(payload=None),
                "provenance": SectionInput(payload={"sources": []}),
                "diagnostics": SectionInput(payload={"items": []}, fallback_reason="partial_data"),
                "limits": SectionInput(payload=None, fallback_reason="soft_limit_defaulted"),
            },
        )
        self.assertEqual(contract.sections["budget"].status, "omitted")
        self.assertEqual(contract.sections["llm_usage"].status, "not_applicable")
        self.assertEqual(contract.sections["provenance"].status, "available")
        self.assertEqual(contract.sections["diagnostics"].status, "fallback")
        self.assertEqual(contract.sections["limits"].status, "fallback")
        self.assertEqual(contract.sections["limits"].payload["fallback_reason"], "soft_limit_defaulted")

    def test_contract_version_and_minimum_semantics(self) -> None:
        contract = build_contract_core(
            capability="review",
            profile="strict",
            summary="summary",
            evidence=({"path": "a.py"},),
            uncertainty=("u1",),
            next_step="run tests",
            section_inputs={
                "action_orchestration": SectionInput(payload={"status": "success", "done_reason": "policy_blocked"}),
            },
        )
        as_dict = contract.as_dict()
        self.assertEqual(as_dict["contract_version"], CONTRACT_VERSION)
        self.assertEqual(as_dict["summary"], "summary")
        self.assertIsInstance(as_dict["evidence"], list)
        self.assertIsInstance(as_dict["uncertainty"], list)
        self.assertEqual(as_dict["next_step"], "run tests")

    def test_diagnostics_policy_limits_are_separated(self) -> None:
        shared_items = [{"code": "x"}]
        contract = build_contract_core(
            capability="query",
            profile="standard",
            summary="ok",
            evidence=(),
            uncertainty=(),
            next_step="next",
            section_inputs={
                "diagnostics": SectionInput(payload={"items": shared_items, "limits": "noise"}),
                "policy_violations": SectionInput(payload={"items": [{"rule": "p1"}], "diagnostics": "noise"}),
                "limits": SectionInput(payload={"limits": {"max": 10}, "items": [{"kind": "budget"}]}),
            },
        )
        diagnostics_payload = contract.sections["diagnostics"].payload
        policy_payload = contract.sections["policy_violations"].payload
        limits_payload = contract.sections["limits"].payload

        self.assertIn("items", diagnostics_payload)
        self.assertNotIn("limits", diagnostics_payload)
        self.assertIn("items", policy_payload)
        self.assertNotIn("diagnostics", policy_payload)
        self.assertIn("limits", limits_payload)

    def test_human_view_derivation_has_no_new_status_logic(self) -> None:
        contract = build_contract_core(
            capability="query",
            profile="standard",
            summary="ok",
            evidence=(),
            uncertainty=(),
            next_step="next",
            section_inputs={
                "action_orchestration": SectionInput(payload={"status": "partial", "done_reason": "policy_blocked"}),
                "budget": SectionInput(payload={"limits": {"max": 10}}),
            },
        )
        view_full = render_view(contract, "full")
        self.assertIn("Done Reason: policy_blocked", view_full)
        self.assertIn("Action Status: partial", view_full)

    def test_validate_contract_schema_flags_invalid_section_status(self) -> None:
        contract = build_contract_core(
            capability="query",
            profile="standard",
            summary="ok",
            evidence=(),
            uncertainty=(),
            next_step="next",
            section_inputs={},
        ).as_dict()

        contract["sections"]["budget"]["status"] = "computed"
        diagnostics = validate_contract_schema(contract)
        self.assertTrue(any(item.code == "invalid_section_status" for item in diagnostics))

    def test_build_contract_core_rejects_unknown_section_inputs(self) -> None:
        with self.assertRaises(ValueError):
            build_contract_core(
                capability="query",
                profile="standard",
                summary="ok",
                evidence=(),
                uncertainty=(),
                next_step="next",
                section_inputs={"unknown_section": SectionInput(payload={"x": 1})},
            )

    def test_render_view_compact_is_explicit_and_omits_next_step(self) -> None:
        contract = build_contract_core(
            capability="query",
            profile="standard",
            summary="ok",
            evidence=(),
            uncertainty=(),
            next_step="run tests",
            section_inputs={},
        )
        compact_view = render_view(contract, "compact")
        self.assertIn("Capability: query", compact_view)
        self.assertNotIn("Next Step:", compact_view)

    def test_render_view_rejects_unknown_view(self) -> None:
        contract = build_contract_core(
            capability="query",
            profile="standard",
            summary="ok",
            evidence=(),
            uncertainty=(),
            next_step="next",
            section_inputs={},
        )
        with self.assertRaises(ValueError):
            render_view(contract, "wide")

    def test_validate_contract_schema_checks_core_section_minimum_semantics(self) -> None:
        contract = build_contract_core(
            capability="query",
            profile="standard",
            summary="ok",
            evidence=(),
            uncertainty=(),
            next_step="next",
            section_inputs={},
        ).as_dict()

        contract["sections"]["action_orchestration"]["status"] = "available"
        contract["sections"]["action_orchestration"]["payload"] = {"status": 1}
        contract["sections"]["budget"]["status"] = "available"
        contract["sections"]["budget"]["payload"] = {}
        contract["sections"]["runtime_settings"]["status"] = "available"
        contract["sections"]["runtime_settings"]["payload"] = {"values": "invalid"}
        contract["sections"]["diagnostics"]["status"] = "available"
        contract["sections"]["diagnostics"]["payload"] = {"items": "invalid"}
        contract["sections"]["policy_violations"]["status"] = "available"
        contract["sections"]["policy_violations"]["payload"] = {"items": "invalid"}
        contract["sections"]["limits"]["status"] = "available"
        contract["sections"]["limits"]["payload"] = {}

        diagnostics = validate_contract_schema(contract)
        diagnostic_codes = {item.code for item in diagnostics}
        self.assertIn("invalid_action_orchestration_status", diagnostic_codes)
        self.assertIn("budget_minimum_semantics_missing", diagnostic_codes)
        self.assertIn("runtime_settings_values_required", diagnostic_codes)
        self.assertIn("diagnostics_items_required", diagnostic_codes)
        self.assertIn("policy_violations_items_required", diagnostic_codes)
        self.assertIn("limits_minimum_semantics_missing", diagnostic_codes)

    def test_normative_status_and_done_reason_not_reinterpreted(self) -> None:
        contract = build_contract_core(
            capability="query",
            profile="standard",
            summary="ok",
            evidence=(),
            uncertainty=(),
            next_step="next",
            section_inputs={
                "action_orchestration": SectionInput(
                    payload={
                        "status": "blocked",
                        "done_reason": "policy_blocked",
                    }
                )
            },
        )
        payload = contract.sections["action_orchestration"].payload
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["done_reason"], "policy_blocked")

    def test_validate_contract_schema_enforces_normative_orchestration_values(self) -> None:
        contract = build_contract_core(
            capability="query",
            profile="standard",
            summary="ok",
            evidence=(),
            uncertainty=(),
            next_step="next",
            section_inputs={},
        ).as_dict()
        contract["sections"]["action_orchestration"]["status"] = "available"
        contract["sections"]["action_orchestration"]["payload"] = {
            "decision": "replan",
            "control_signal": "pause",
            "done_reason": "unknown_reason",
        }
        diagnostics = validate_contract_schema(contract)
        diagnostic_codes = {item.code for item in diagnostics}
        self.assertIn("invalid_action_orchestration_decision_value", diagnostic_codes)
        self.assertIn("invalid_action_orchestration_control_signal", diagnostic_codes)
        self.assertIn("invalid_action_orchestration_done_reason_value", diagnostic_codes)


if __name__ == "__main__":
    unittest.main()

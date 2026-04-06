from __future__ import annotations

import unittest
from pathlib import Path

from core.toml_compat import tomli


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"

EXPECTED_MUTATION_PATHS: tuple[str, ...] = (
    "core/mode_execution_foundation.py",
    "core/runtime_settings_foundation.py",
    "core/runtime_settings_foundation_registry.py",
    "core/workspace_foundation.py",
    "core/workspace_locators.py",
    "core/workspace_scope_rules.py",
    "core/workspace_roles.py",
    "core/observability_foundation.py",
    "core/orchestration_foundation.py",
    "core/retrieval_foundation.py",
    "core/evidence_ranking_foundation.py",
    "core/target_resolution_foundation.py",
)

EXPECTED_TEST_PATHS: tuple[str, ...] = (
    "tests/test_mode_execution_foundation.py",
    "tests/test_runtime_settings_foundation.py",
    "tests/test_runtime_settings_foundation_registry.py",
    "tests/test_workspace_foundation.py",
    "tests/test_observability_foundation.py",
    "tests/test_orchestration_foundation.py",
    "tests/test_retrieval_foundation.py",
    "tests/test_evidence_ranking_foundation.py",
    "tests/test_target_resolution_foundation.py",
)


class MutationInfrastructureTests(unittest.TestCase):
    def test_mutmut_config_targets_foundation_modules_and_tests(self) -> None:
        payload = tomli.loads(PYPROJECT.read_text(encoding="utf-8"))
        tool = payload.get("tool", {})
        self.assertIsInstance(tool, dict)
        mutmut_config = tool.get("mutmut")
        self.assertIsInstance(mutmut_config, dict)

        paths_to_mutate = mutmut_config.get("paths_to_mutate")
        self.assertEqual(paths_to_mutate, list(EXPECTED_MUTATION_PATHS))

        tests_dir = mutmut_config.get("tests_dir")
        self.assertEqual(tests_dir, list(EXPECTED_TEST_PATHS))

        for relative_path in EXPECTED_MUTATION_PATHS + EXPECTED_TEST_PATHS:
            self.assertTrue((ROOT / relative_path).exists(), f"Configured mutmut path does not exist: {relative_path}")


if __name__ == "__main__":
    unittest.main()

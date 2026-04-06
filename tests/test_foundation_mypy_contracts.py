from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

IMPLEMENTED_FOUNDATION_MYPY_FILES: tuple[str, ...] = (
    "core/mode_execution_foundation.py",
    "core/runtime_settings_foundation.py",
    "core/runtime_settings_foundation_registry.py",
    "core/workspace_foundation.py",
    "core/workspace_locators.py",
    "core/workspace_scope_rules.py",
    "core/workspace_roles.py",
    "core/output_contract_foundation.py",
    "core/observability_foundation.py",
    "core/orchestration_foundation.py",
    "core/retrieval_foundation.py",
    "core/evidence_ranking_foundation.py",
    "core/target_resolution_foundation.py",
)

ROOT = Path(__file__).resolve().parents[1]


class FoundationMypyContractsTests(unittest.TestCase):
    def test_foundation_modules_pass_mypy_contract_gate(self) -> None:
        process = subprocess.run(
            [sys.executable, "-m", "mypy", *IMPLEMENTED_FOUNDATION_MYPY_FILES],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if process.returncode != 0:
            self.fail(
                "Implemented foundation mypy contract gate failed.\n"
                f"STDOUT:\n{process.stdout}\n"
                f"STDERR:\n{process.stderr}"
            )


if __name__ == "__main__":
    unittest.main()

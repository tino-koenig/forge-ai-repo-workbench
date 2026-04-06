from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from scripts.run_quality_gates import (
    FOUNDATION_MYPY_EXCLUDED_ROOTS,
    IMPLEMENTED_FOUNDATION_MYPY_FILES,
    REPO_WIDE_MYPY_EXCLUDED_ROOTS,
    REPO_WIDE_MYPY_PATHS,
    GateError,
    _extract_mypy_error_count,
    _typing_scope_metadata,
    gate_repo_wide_mypy_baseline,
)


class RepoWideMypyBaselineGateTests(unittest.TestCase):
    def test_typing_scope_metadata_is_explicit_and_aligned(self) -> None:
        foundation_scope = _typing_scope_metadata("foundation")
        repo_scope = _typing_scope_metadata("repo_wide")

        self.assertEqual(foundation_scope["includes"], IMPLEMENTED_FOUNDATION_MYPY_FILES)
        self.assertEqual(foundation_scope["excludes"], FOUNDATION_MYPY_EXCLUDED_ROOTS)
        self.assertEqual(foundation_scope["pass_semantics"], "scoped_success_only")

        self.assertEqual(repo_scope["includes"], REPO_WIDE_MYPY_PATHS)
        self.assertEqual(repo_scope["excludes"], REPO_WIDE_MYPY_EXCLUDED_ROOTS)
        self.assertEqual(repo_scope["pass_semantics"], "baseline_non_regression_only")

    def test_typing_scope_metadata_rejects_unknown_gate(self) -> None:
        with self.assertRaises(GateError):
            _typing_scope_metadata("unknown")

    def test_extract_mypy_error_count_from_summary(self) -> None:
        proc = subprocess.CompletedProcess(
            args=["mypy"],
            returncode=1,
            stdout="Found 206 errors in 22 files (checked 80 source files)\n",
            stderr="",
        )
        self.assertEqual(_extract_mypy_error_count(proc), 206)

    def test_extract_mypy_error_count_falls_back_to_error_lines(self) -> None:
        proc = subprocess.CompletedProcess(
            args=["mypy"],
            returncode=1,
            stdout="core/a.py:10: error: bad\nmodes/b.py:12: error: bad\n",
            stderr="",
        )
        self.assertEqual(_extract_mypy_error_count(proc), 2)

    @patch("scripts.run_quality_gates._select_mypy_command", return_value=["python", "-m", "mypy"])
    @patch("scripts.run_quality_gates.run_cmd")
    def test_repo_wide_mypy_baseline_allows_at_baseline(self, run_cmd_mock, _) -> None:
        run_cmd_mock.return_value = subprocess.CompletedProcess(
            args=["python", "-m", "mypy"],
            returncode=1,
            stdout="Found 206 errors in 22 files (checked 80 source files)\n",
            stderr="",
        )
        gate_repo_wide_mypy_baseline()

    @patch("scripts.run_quality_gates._select_mypy_command", return_value=["python", "-m", "mypy"])
    @patch("scripts.run_quality_gates.run_cmd")
    def test_repo_wide_mypy_baseline_rejects_regression(self, run_cmd_mock, _) -> None:
        run_cmd_mock.return_value = subprocess.CompletedProcess(
            args=["python", "-m", "mypy"],
            returncode=1,
            stdout="Found 207 errors in 22 files (checked 80 source files)\n",
            stderr="",
        )
        with self.assertRaises(GateError):
            gate_repo_wide_mypy_baseline()


if __name__ == "__main__":
    unittest.main()

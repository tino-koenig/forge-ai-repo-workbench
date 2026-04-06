from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.workspace_foundation import (
    DECISION_ALLOW,
    DECISION_DENY,
    compute_workspace_snapshot_id,
    resolve_workspace_context,
)
from core.workspace_locators import normalize_locator
from core.workspace_roles import classify_file_role
from core.workspace_scope_rules import is_in_read_scope, is_in_write_scope


class WorkspaceFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._temp_dir.name)

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def _workspace(self, args: dict | None = None):
        return resolve_workspace_context(args or {}, self.repo_root)

    def test_workspace_snapshot_id_is_deterministic(self) -> None:
        args = {
            "read_scopes": [str(self.repo_root / "src"), str(self.repo_root / "docs")],
            "write_scopes": [str(self.repo_root / "src")],
            "ignore_repo": ["build/**"],
            "include_cli": ["src/**"],
        }
        workspace_a = self._workspace(args)
        workspace_b = self._workspace(args)

        self.assertEqual(workspace_a.workspace_status, "ok")
        self.assertEqual(workspace_a.workspace_snapshot_id, workspace_b.workspace_snapshot_id)
        self.assertEqual(workspace_a.workspace_snapshot_id, compute_workspace_snapshot_id(workspace_a))

        workspace_c = self._workspace({**args, "write_scopes": [str(self.repo_root / "docs")]})
        self.assertNotEqual(workspace_a.workspace_snapshot_id, workspace_c.workspace_snapshot_id)

    def test_workspace_snapshot_id_ignores_diagnostics_and_status(self) -> None:
        workspace_ok = self._workspace({"platform_case_policy": "sensitive"})
        workspace_partial = self._workspace({"platform_case_policy": "invalid"})

        self.assertEqual(workspace_ok.workspace_status, "ok")
        self.assertEqual(workspace_partial.workspace_status, "partial")
        self.assertNotEqual(workspace_ok.diagnostics, workspace_partial.diagnostics)
        self.assertEqual(workspace_ok.workspace_snapshot_id, workspace_partial.workspace_snapshot_id)

    def test_repo_roots_are_deduplicated_and_git_not_default_artifact_root(self) -> None:
        duplicate = str(self.repo_root / ".")
        workspace = self._workspace({"repo_roots": [str(self.repo_root), duplicate]})

        self.assertEqual(len(workspace.repo_roots), 1)
        self.assertEqual(workspace.repo_roots[0], self.repo_root.resolve().as_posix())
        self.assertTrue(any(root.endswith("/.forge") for root in workspace.artifact_roots))
        self.assertFalse(any(root.endswith("/.git") for root in workspace.artifact_roots))

    def test_normalize_locator_normalizes_paths_and_refs(self) -> None:
        workspace = self._workspace()

        path_locator = normalize_locator("src/../src/main.py", workspace)
        self.assertEqual(path_locator.locator_kind, "path")
        self.assertEqual(path_locator.workspace_relative_path, "src/main.py")
        self.assertTrue(path_locator.locator.endswith("/src/main.py"))
        expected_locator = Path(
            os.path.normpath(str((Path(workspace.workspace_root) / path_locator.workspace_relative_path).absolute()))
        ).as_posix()
        self.assertEqual(expected_locator, path_locator.locator)

        url_locator = normalize_locator("https://example.com/ref", workspace)
        self.assertEqual(url_locator.locator_kind, "url")
        self.assertIsNone(url_locator.workspace_relative_path)

        virtual_locator = normalize_locator("virtual:entrypoint", workspace)
        self.assertEqual(virtual_locator.locator_kind, "virtual")
        self.assertIsNone(virtual_locator.workspace_relative_path)

    def test_locator_uses_consistent_lexical_path_for_symlink_inputs(self) -> None:
        (self.repo_root / "real").mkdir(parents=True, exist_ok=True)
        (self.repo_root / "real" / "target.py").write_text("x = 1\n", encoding="utf-8")
        (self.repo_root / "src").mkdir(parents=True, exist_ok=True)
        (self.repo_root / "src" / "link.py").symlink_to(self.repo_root / "real" / "target.py")

        workspace_block = self._workspace({"allow_symlinks": False})
        locator_block = normalize_locator("src/link.py", workspace_block)
        self.assertTrue(locator_block.locator.endswith("/src/link.py"))
        self.assertEqual(locator_block.workspace_relative_path, "src/link.py")

        workspace_allow = self._workspace({"allow_symlinks": True})
        locator_allow = normalize_locator("src/link.py", workspace_allow)
        self.assertEqual(locator_allow.locator, locator_block.locator)
        self.assertEqual(locator_allow.workspace_relative_path, locator_block.workspace_relative_path)

    def test_read_write_scope_and_write_deny_by_default(self) -> None:
        workspace = self._workspace()
        locator = normalize_locator("src/service.py", workspace)

        read_decision = is_in_read_scope(locator, workspace)
        write_decision = is_in_write_scope(locator, workspace)

        self.assertEqual(read_decision.decision, DECISION_ALLOW)
        self.assertTrue(read_decision.allowed)
        self.assertEqual(read_decision.decision_type, "read")
        self.assertEqual(read_decision.matched_rule_id, read_decision.rule_id)
        self.assertFalse(read_decision.policy_relevant)
        self.assertEqual(write_decision.decision, DECISION_DENY)
        self.assertFalse(write_decision.allowed)
        self.assertEqual(write_decision.decision_type, "write")
        self.assertEqual(write_decision.matched_rule_id, write_decision.rule_id)
        self.assertTrue(write_decision.policy_relevant)
        self.assertEqual(write_decision.reason_code, "write_scope_deny_by_default")
        self.assertTrue(any(d.code == "write_scope_deny_by_default" for d in write_decision.diagnostics))

    def test_read_and_write_scope_split_with_write_scope_restriction(self) -> None:
        workspace = self._workspace(
            {
                "write_scopes": [str(self.repo_root / "src")],
            }
        )

        src_locator = normalize_locator("src/service.py", workspace)
        docs_locator = normalize_locator("docs/readme.md", workspace)

        self.assertEqual(is_in_write_scope(src_locator, workspace).decision, DECISION_ALLOW)

        docs_write = is_in_write_scope(docs_locator, workspace)
        self.assertEqual(docs_write.decision, DECISION_DENY)
        self.assertEqual(docs_write.reason_code, "outside_write_scope")

    def test_workspace_blocks_when_write_scope_is_outside_read_scope(self) -> None:
        workspace = self._workspace(
            {
                "read_scopes": [str(self.repo_root / "src")],
                "write_scopes": [str(self.repo_root / "docs")],
            }
        )
        self.assertEqual(workspace.workspace_status, "blocked")
        self.assertTrue(any(d.code == "write_scope_outside_read_scope" for d in workspace.diagnostics))

        locator = normalize_locator("src/service.py", workspace)
        write_decision = is_in_write_scope(locator, workspace)
        self.assertEqual(write_decision.decision, DECISION_DENY)
        self.assertEqual(write_decision.reason_code, "workspace_blocked")
        self.assertTrue(write_decision.policy_relevant)

    def test_include_ignore_priority_default_repo_local_cli(self) -> None:
        workspace_repo_override = self._workspace(
            {
                "ignore_default": ["generated/**"],
                "include_repo": ["generated/safe/**"],
            }
        )
        locator = normalize_locator("generated/safe/output.py", workspace_repo_override)

        repo_decision = is_in_read_scope(locator, workspace_repo_override)
        self.assertEqual(repo_decision.decision, DECISION_ALLOW)
        self.assertIsNotNone(repo_decision.matched_rule_id)
        self.assertEqual(repo_decision.matched_rule_source, "repo")
        self.assertTrue(any(d.code == "scope_rule_conflict_resolved" for d in repo_decision.diagnostics))
        self.assertTrue(any(d.code == "scope_rule_conflict_loser" for d in repo_decision.diagnostics))
        self.assertTrue(any(d.rule_source == "repo" for d in repo_decision.diagnostics if d.code == "scope_rule_conflict_resolved"))

        workspace_cli_override = self._workspace(
            {
                "ignore_default": ["generated/**"],
                "include_repo": ["generated/safe/**"],
                "ignore_cli": ["generated/safe/**"],
            }
        )
        cli_decision = is_in_read_scope(locator, workspace_cli_override)
        self.assertEqual(cli_decision.decision, DECISION_DENY)
        self.assertEqual(cli_decision.reason_code, "scope_rule_conflict_resolved")
        self.assertEqual(cli_decision.matched_rule_source, "cli")
        self.assertTrue(any(d.rule_source == "cli" for d in cli_decision.diagnostics if d.code == "scope_rule_conflict_resolved"))

    def test_role_classification(self) -> None:
        workspace = self._workspace()

        source_role = classify_file_role(normalize_locator("src/app.py", workspace), workspace)
        config_role = classify_file_role(normalize_locator("settings.toml", workspace), workspace)
        test_role = classify_file_role(normalize_locator("tests/test_app.py", workspace), workspace)
        docs_role = classify_file_role(normalize_locator("docs/guide.md", workspace), workspace)
        generated_role = classify_file_role(normalize_locator("dist/bundle.min.js", workspace), workspace)
        artifact_role = classify_file_role(normalize_locator(".forge/runs.jsonl", workspace), workspace)
        external_role = classify_file_role(normalize_locator("../outside.py", workspace), workspace)

        self.assertEqual(source_role.role, "source")
        self.assertEqual(config_role.role, "config")
        self.assertEqual(test_role.role, "test")
        self.assertEqual(docs_role.role, "docs")
        self.assertEqual(generated_role.role, "generated")
        self.assertEqual(artifact_role.role, "artifact")
        self.assertEqual(external_role.role, "external")

    def test_structured_diagnostics_for_ignore_block_and_conflict(self) -> None:
        workspace = self._workspace(
            {
                "ignore_cli": ["blocked/**"],
                "ignore_default": ["conflict/**"],
                "include_local": ["conflict/**"],
            }
        )

        blocked = normalize_locator("blocked/a.py", workspace)
        blocked_decision = is_in_read_scope(blocked, workspace)
        self.assertEqual(blocked_decision.decision, DECISION_DENY)
        self.assertEqual(blocked_decision.reason_code, "scope_rule_conflict_resolved")
        self.assertEqual(blocked_decision.decision_type, "read")
        self.assertFalse(blocked_decision.allowed)
        self.assertTrue(blocked_decision.policy_relevant)

        ignored_diag = blocked_decision.diagnostics[0]
        self.assertIsNotNone(ignored_diag.rule_id)
        self.assertEqual(ignored_diag.rule_source, "cli")
        self.assertIsNotNone(ignored_diag.rule_priority)

        blocked_write = is_in_write_scope(blocked, workspace)
        self.assertEqual(blocked_write.reason_code, "write_requires_read_scope")
        self.assertTrue(any(d.code == "scope_rule_conflict_resolved" for d in blocked_write.diagnostics))

        conflict = normalize_locator("conflict/a.py", workspace)
        conflict_decision = is_in_read_scope(conflict, workspace)
        self.assertEqual(conflict_decision.decision, DECISION_ALLOW)
        conflict_diag = next(d for d in conflict_decision.diagnostics if d.code == "scope_rule_conflict_resolved")
        self.assertIsNotNone(conflict_diag.rule_id)
        self.assertEqual(conflict_diag.rule_source, "local")
        self.assertIsNotNone(conflict_diag.rule_priority)

    def test_symlink_policy_blocks_when_disabled(self) -> None:
        (self.repo_root / "real").mkdir(parents=True, exist_ok=True)
        (self.repo_root / "real" / "target.py").write_text("x = 1\n", encoding="utf-8")
        (self.repo_root / "src").mkdir(parents=True, exist_ok=True)
        (self.repo_root / "src" / "link.py").symlink_to(self.repo_root / "real" / "target.py")

        workspace = self._workspace({"allow_symlinks": False})
        locator = normalize_locator("src/link.py", workspace)
        read_decision = is_in_read_scope(locator, workspace)
        self.assertEqual(read_decision.decision, DECISION_DENY)
        self.assertEqual(read_decision.reason_code, "symlink_not_allowed")

        workspace_allowed = self._workspace({"allow_symlinks": True})
        locator_allowed = normalize_locator("src/link.py", workspace_allowed)
        allowed_decision = is_in_read_scope(locator_allowed, workspace_allowed)
        self.assertEqual(allowed_decision.decision, DECISION_ALLOW)

    def test_symlink_policy_blocks_nonexistent_target_in_symlink_chain(self) -> None:
        (self.repo_root / "real").mkdir(parents=True, exist_ok=True)
        (self.repo_root / "src").mkdir(parents=True, exist_ok=True)
        (self.repo_root / "src" / "linked").symlink_to(self.repo_root / "real", target_is_directory=True)

        workspace = self._workspace({"allow_symlinks": False, "write_scopes": [str(self.repo_root / "src")]})
        locator = normalize_locator("src/linked/missing.py", workspace)

        read_decision = is_in_read_scope(locator, workspace)
        self.assertEqual(read_decision.decision, DECISION_DENY)
        self.assertEqual(read_decision.reason_code, "symlink_not_allowed")

        write_decision = is_in_write_scope(locator, workspace)
        self.assertEqual(write_decision.decision, DECISION_DENY)
        self.assertEqual(write_decision.reason_code, "write_requires_read_scope")
        self.assertTrue(any(d.code == "symlink_not_allowed" for d in write_decision.diagnostics))

        workspace_allowed = self._workspace({"allow_symlinks": True, "write_scopes": [str(self.repo_root / "src")]})
        allowed_locator = normalize_locator("src/linked/missing.py", workspace_allowed)
        allowed_read = is_in_read_scope(allowed_locator, workspace_allowed)
        allowed_write = is_in_write_scope(allowed_locator, workspace_allowed)
        self.assertEqual(allowed_read.decision, DECISION_ALLOW)
        self.assertEqual(allowed_write.decision, DECISION_ALLOW)

    def test_case_policy_insensitive_for_scope_and_roles(self) -> None:
        workspace = self._workspace(
            {
                "platform_case_policy": "insensitive",
                "ignore_default": ["SRC/GENERATED/**"],
                "write_scopes": [str(self.repo_root / "SRC")],
            }
        )
        locator = normalize_locator("src/generated/Out.PY", workspace)
        read_decision = is_in_read_scope(locator, workspace)
        self.assertEqual(read_decision.decision, DECISION_DENY)
        self.assertIn(read_decision.reason_code, ("ignored_by_rule", "scope_rule_conflict_resolved"))

        role = classify_file_role(normalize_locator("DOCS/Guide.MD", workspace), workspace)
        self.assertEqual(role.role, "docs")

    def test_role_classification_diagnoses_multiple_role_matches(self) -> None:
        workspace = self._workspace()
        role = classify_file_role(normalize_locator("tests/readme.md", workspace), workspace)
        self.assertEqual(role.role, "test")
        self.assertTrue(any(d.code == "multiple_role_matches" for d in role.diagnostics))
        diagnostic = role.diagnostics[0]
        self.assertIn("alternatives=docs", diagnostic.message)

    def test_workspace_status_partial_for_non_blocking_workspace_diagnostic(self) -> None:
        workspace = self._workspace({"platform_case_policy": "invalid"})
        self.assertEqual(workspace.workspace_status, "partial")
        self.assertTrue(any(d.code == "invalid_platform_case_policy" for d in workspace.diagnostics))


if __name__ == "__main__":
    unittest.main()

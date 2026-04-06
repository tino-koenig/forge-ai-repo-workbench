from __future__ import annotations

import unittest

from core.target_resolution_foundation import (
    FromRunReference,
    ResolutionPolicy,
    TargetCandidate,
    TargetRequest,
    TargetResolutionContext,
    order_target_candidates_for_resolution,
    resolve_from_run_reference,
    resolve_target,
    validate_transition,
)


class TargetResolutionFoundationTests(unittest.TestCase):
    def _context(self) -> TargetResolutionContext:
        candidates = (
            TargetCandidate(
                kind="symbol",
                path="/repo/a.py",
                symbol="compute_price",
                resolution_priority=350,
                rationale="exact symbol candidate",
                source="ranking",
                metadata={"evidence_anchors": ({"path": "/repo/a.py", "line": 10, "text": "compute_price"},)},
            ),
            TargetCandidate(
                kind="symbol",
                path="/repo/b.py",
                symbol="compute_price",
                resolution_priority=350,
                rationale="same symbol candidate",
                source="ranking",
                metadata={"evidence_anchors": ({"path": "/repo/b.py", "line": 12, "text": "compute_price"},)},
            ),
            TargetCandidate(
                kind="symbol",
                path="/repo/c.py",
                symbol="other_symbol",
                resolution_priority=300,
                rationale="different symbol",
                source="ranking",
            ),
        )
        from_run = {
            "run-123": FromRunReference(
                run_id="run-123",
                resolved_target="/repo/a.py",
                resolved_kind="path",
                resolved_path="/repo/a.py",
                resolved_symbol=None,
                source_capability="explain",
                source_mode="explain",
                strategy="exact",
                evidence_anchors=({"path": "/repo/a.py", "line": 10, "text": "anchor"},),
                transition_meta={"handoff_id": "handoff-1"},
            )
        }
        return TargetResolutionContext(
            candidate_pool=candidates,
            known_paths=("/repo/a.py", "/repo/b.py"),
            known_directories=("/repo/src",),
            repo_root="/repo",
            from_run_references=from_run,
            allowed_transitions=(("explain", "review"), ("review", "explain"), ("explain", "explain")),
            policy=ResolutionPolicy(ambiguity_top_k=2, allow_directory_fallback=True, allow_repo_fallback=True),
            run_id="run-x",
            trace_id="trace-x",
            workspace_snapshot_id="ws-x",
        )

    def test_normal_target_resolution_explicit_path(self) -> None:
        result = resolve_target(
            TargetRequest(raw_target="/repo/a.py", capability="explain", profile="standard"),
            self._context(),
        )
        self.assertEqual(result.resolution_status, "resolved")
        self.assertEqual(result.resolved_kind, "path")
        self.assertEqual(result.resolved_target, "/repo/a.py")

    def test_ambiguity_and_top_k(self) -> None:
        result = resolve_target(
            TargetRequest(raw_target="compute_price", capability="explain", profile="standard"),
            self._context(),
        )
        self.assertEqual(result.resolution_status, "ambiguous")
        self.assertEqual(len(result.ambiguity_top_k), 2)
        self.assertTrue(any(d.code == "ambiguous_target" for d in result.diagnostics))

    def test_fallback_visibility(self) -> None:
        context = self._context()
        result = resolve_target(
            TargetRequest(raw_target="unknown_target", capability="explain", profile="standard"),
            context,
        )
        self.assertEqual(result.resolution_status, "resolved")
        self.assertEqual(result.resolution_source, "fallback")
        self.assertEqual(result.resolution_strategy, "policy_fallback")
        self.assertTrue(any(d.code == "fallback_resolution_applied" for d in result.diagnostics))

    def test_resolved_target_is_central_representation(self) -> None:
        result = resolve_target(
            TargetRequest(raw_target="/repo/a.py", capability="explain", profile="standard"),
            self._context(),
        )
        self.assertEqual(result.resolved_target, result.resolved_path)
        self.assertIsNone(result.resolved_symbol)

    def test_from_run_reference_resolution(self) -> None:
        request = TargetRequest(raw_target="ignored", capability="review", profile="standard", from_run="run-123")
        result = resolve_from_run_reference(request, self._context())
        self.assertEqual(result.resolution_status, "resolved")
        self.assertEqual(result.resolution_source, "from_run")
        self.assertEqual(result.resolved_kind, "path")
        self.assertEqual(result.transition_meta.get("from_run"), "run-123")

    def test_transition_validation_blocked(self) -> None:
        context = self._context()
        transition = validate_transition("explain", "query", context)
        self.assertFalse(transition.allowed)
        self.assertEqual(transition.status, "blocked")

    def test_from_run_blocked_transition(self) -> None:
        request = TargetRequest(raw_target="ignored", capability="query", profile="standard", from_run="run-123")
        result = resolve_from_run_reference(request, self._context())
        self.assertEqual(result.resolution_status, "blocked")
        self.assertTrue(any(d.code == "transition_blocked" for d in result.diagnostics))

    def test_deterministic_candidate_ordering(self) -> None:
        candidates = (
            TargetCandidate(kind="symbol", path="/z.py", symbol="x", resolution_priority=100, rationale="a", source="s1"),
            TargetCandidate(kind="symbol", path="/a.py", symbol="x", resolution_priority=100, rationale="a", source="s1"),
            TargetCandidate(kind="path", path="/b.py", symbol=None, resolution_priority=500, rationale="a", source="s1"),
        )
        ordered_a = order_target_candidates_for_resolution(candidates, ResolutionPolicy())
        ordered_b = order_target_candidates_for_resolution(tuple(reversed(candidates)), ResolutionPolicy())
        self.assertEqual(ordered_a, ordered_b)
        self.assertEqual(ordered_a[0].kind, "path")

    def test_unresolved_explicit_target_blocks_fallback_when_policy_requires(self) -> None:
        context = self._context()
        strict = TargetResolutionContext(
            candidate_pool=context.candidate_pool,
            known_paths=context.known_paths,
            known_directories=context.known_directories,
            repo_root=context.repo_root,
            from_run_references=context.from_run_references,
            allowed_transitions=context.allowed_transitions,
            policy=ResolutionPolicy(
                ambiguity_top_k=2,
                allow_directory_fallback=True,
                allow_repo_fallback=True,
                unresolved_explicit_target_blocks_fallback=True,
            ),
        )
        result = resolve_target(
            TargetRequest(raw_target="/repo/missing.py", capability="explain", profile="standard"),
            strict,
        )
        self.assertEqual(result.resolution_status, "unresolved")
        self.assertEqual(result.resolution_source, "explicit_path")

    def test_candidate_kind_is_runtime_validated(self) -> None:
        with self.assertRaises(ValueError):
            TargetCandidate(
                kind="from_run_reference",  # type: ignore[arg-type]
                path="/repo/a.py",
                symbol=None,
                resolution_priority=100,
                rationale="invalid",
                source="test",
            )

    def test_explicit_path_detection_is_more_robust(self) -> None:
        result = resolve_target(
            TargetRequest(raw_target="./src/missing.txt", capability="explain", profile="standard"),
            self._context(),
        )
        self.assertEqual(result.resolution_source, "explicit_path")
        self.assertEqual(result.resolution_status, "unresolved")
        self.assertTrue(any(d.code == "unresolved_path" for d in result.diagnostics))

    def test_constraints_and_hints_are_used_for_resolution(self) -> None:
        context = self._context()
        request = TargetRequest(
            raw_target="compute_price",
            capability="explain",
            profile="standard",
            constraints={"allowed_candidate_kinds": ("symbol",), "allow_fallback": False},
            target_hints={"preferred_path_prefix": "/repo/b.py"},
        )
        result = resolve_target(request, context)
        self.assertEqual(result.resolution_status, "ambiguous")
        self.assertTrue(result.ambiguity_top_k)
        self.assertEqual(result.ambiguity_top_k[0].path, "/repo/b.py")


if __name__ == "__main__":
    unittest.main()

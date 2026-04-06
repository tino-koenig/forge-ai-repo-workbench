from __future__ import annotations

import unittest

from core.evidence_ranking_foundation import (
    COMPONENT_EVIDENCE_COUNT,
    COMPONENT_RERANK_LOCATOR_TERM_MATCH,
    COMPONENT_RETRIEVAL_RAW_SCORE,
    RankingContext,
    RankingDiagnostic,
    RankingPolicy,
    RankingRequest,
    default_ranking_policy,
    rank_evidence,
    rerank_ranking_policy,
)
from core.retrieval_foundation import (
    RETRIEVAL_CONTRACT_VERSION,
    RetrievalCandidate,
    RetrievalDiagnostic,
    RetrievalEvidence,
    RetrievalOutcome,
)


class EvidenceRankingFoundationTests(unittest.TestCase):
    def _retrieval_outcome(self) -> RetrievalOutcome:
        candidates = (
            RetrievalCandidate(
                path_or_url="/repo/a.py",
                locator="/repo/a.py",
                locator_kind="path",
                source_type="repo",
                source_origin="repo-index",
                retrieval_source="repo_scan",
                retrieval_signals=("symbol:compute_price",),
                raw_retrieval_score=1.0,
                merged_source_types=("repo",),
                merged_source_origins=("repo-index",),
                merged_retrieval_sources=("repo_scan",),
            ),
            RetrievalCandidate(
                path_or_url="/repo/b.py",
                locator="/repo/b.py",
                locator_kind="path",
                source_type="framework",
                source_origin="framework-docs",
                retrieval_source="framework_adapter",
                retrieval_signals=("keyword:compute_price",),
                raw_retrieval_score=1.0,
                merged_source_types=("framework",),
                merged_source_origins=("framework-docs",),
                merged_retrieval_sources=("framework_adapter",),
            ),
        )
        evidence = (
            RetrievalEvidence(
                path_or_url="/repo/a.py",
                locator="/repo/a.py",
                locator_kind="path",
                line=10,
                text="compute_price implementation",
                term="compute_price",
                retrieval_source="repo_scan",
                source_type="repo",
                source_origin="repo-index",
                retrieval_signals=("symbol:compute_price",),
                merged_source_types=("repo",),
                merged_source_origins=("repo-index",),
                merged_retrieval_sources=("repo_scan",),
            ),
            RetrievalEvidence(
                path_or_url="/repo/b.py",
                locator="/repo/b.py",
                locator_kind="path",
                line=11,
                text="compute_price mention",
                term="compute_price",
                retrieval_source="framework_adapter",
                source_type="framework",
                source_origin="framework-docs",
                retrieval_signals=("keyword:compute_price",),
                merged_source_types=("framework",),
                merged_source_origins=("framework-docs",),
                merged_retrieval_sources=("framework_adapter",),
            ),
        )
        return RetrievalOutcome(
            retrieval_contract_version=RETRIEVAL_CONTRACT_VERSION,
            candidates=candidates,
            evidence_items=evidence,
            retrieval_diagnostics=(RetrievalDiagnostic(code="x", message="x", severity="info"),),
            source_usage=tuple(),
            status="ok",
        )

    def test_deterministic_ranking_for_same_input(self) -> None:
        outcome = self._retrieval_outcome()
        request = RankingRequest(query_terms=("compute_price",), enable_rerank=False)
        context = RankingContext(policy=default_ranking_policy())
        first = rank_evidence(request, outcome, context)
        second = rank_evidence(request, outcome, context)
        self.assertEqual(first.ranked_candidates, second.ranked_candidates)
        self.assertEqual(first.tie_break_decisions, second.tie_break_decisions)
        self.assertEqual(first.diagnostics, second.diagnostics)

    def test_score_components_and_aggregation(self) -> None:
        outcome = self._retrieval_outcome()
        request = RankingRequest(query_terms=("compute_price",), enable_rerank=False)
        ranked = rank_evidence(request, outcome, RankingContext(policy=default_ranking_policy()))
        candidate = ranked.ranked_candidates[0]
        component_ids = {component.component_id for component in candidate.score_components}
        self.assertIn(COMPONENT_RETRIEVAL_RAW_SCORE, component_ids)
        self.assertIn(COMPONENT_EVIDENCE_COUNT, component_ids)
        self.assertGreater(candidate.score_total, 0.0)

    def test_tie_break_is_stable(self) -> None:
        outcome = self._retrieval_outcome()
        policy = default_ranking_policy()
        ranked = rank_evidence(
            RankingRequest(query_terms=("compute_price",), enable_rerank=False),
            outcome,
            RankingContext(policy=policy),
        )
        self.assertEqual(ranked.ranked_candidates[0].locator, "/repo/a.py")
        self.assertTrue(isinstance(ranked.tie_break_decisions, tuple))

    def test_policy_id_and_version_visible(self) -> None:
        outcome = self._retrieval_outcome()
        policy = default_ranking_policy()
        ranked = rank_evidence(
            RankingRequest(query_terms=("compute_price",), enable_rerank=False),
            outcome,
            RankingContext(policy=policy),
        )
        self.assertEqual(ranked.policy_id, policy.policy_id)
        self.assertEqual(ranked.policy_version, policy.policy_version)
        self.assertEqual(ranked.ranking_policy_id, policy.policy_id)
        self.assertEqual(ranked.ranking_policy_version, policy.policy_version)
        self.assertEqual(ranked.candidates, ranked.ranked_candidates)
        self.assertEqual(ranked.candidates[0].policy_id, policy.policy_id)
        self.assertEqual(ranked.candidates[0].ranking_policy_id, policy.policy_id)

    def test_explainability_fields_present(self) -> None:
        ranked = rank_evidence(
            RankingRequest(query_terms=("compute_price",), enable_rerank=False),
            self._retrieval_outcome(),
            RankingContext(policy=default_ranking_policy()),
        )
        explanation = ranked.ranked_candidates[0].explanation
        self.assertTrue(explanation)
        self.assertTrue(any("retrieval_raw_score" in line for line in explanation))

    def test_rerank_step_declared_not_hidden(self) -> None:
        outcome = self._retrieval_outcome()
        request = RankingRequest(query_terms=("a.py",), enable_rerank=True)
        ranked = rank_evidence(request, outcome, RankingContext(policy=rerank_ranking_policy()))
        first = ranked.ranked_candidates[0]
        component_ids = {component.component_id for component in first.score_components}
        self.assertIn(COMPONENT_RETRIEVAL_RAW_SCORE, component_ids)
        self.assertIn(COMPONENT_RERANK_LOCATOR_TERM_MATCH, component_ids)
        self.assertTrue(any(item.code == "rerank_applied" for item in ranked.diagnostics))

    def test_status_and_diagnostic_behavior(self) -> None:
        retrieval_error = RetrievalOutcome(
            retrieval_contract_version=RETRIEVAL_CONTRACT_VERSION,
            candidates=tuple(),
            evidence_items=tuple(),
            retrieval_diagnostics=tuple(),
            source_usage=tuple(),
            status="error",
        )
        ranked_error = rank_evidence(
            RankingRequest(query_terms=("x",), enable_rerank=False),
            retrieval_error,
            RankingContext(policy=default_ranking_policy()),
        )
        self.assertEqual(ranked_error.status, "error")
        self.assertTrue(any(item.code == "retrieval_error" for item in ranked_error.diagnostics))

        partial_retrieval = RetrievalOutcome(
            retrieval_contract_version=RETRIEVAL_CONTRACT_VERSION,
            candidates=self._retrieval_outcome().candidates,
            evidence_items=self._retrieval_outcome().evidence_items,
            retrieval_diagnostics=tuple(),
            source_usage=tuple(),
            status="partial",
        )
        ranked_partial = rank_evidence(
            RankingRequest(query_terms=("compute_price",), enable_rerank=False),
            partial_retrieval,
            RankingContext(policy=default_ranking_policy()),
        )
        self.assertEqual(ranked_partial.status, "partial")

    def test_top_k_truncation_diagnostic(self) -> None:
        ranked = rank_evidence(
            RankingRequest(query_terms=("compute_price",), enable_rerank=False, top_k=1),
            self._retrieval_outcome(),
            RankingContext(policy=default_ranking_policy()),
        )
        self.assertEqual(len(ranked.ranked_candidates), 1)
        self.assertTrue(any(item.code == "ranking_top_k_applied" for item in ranked.diagnostics))

    def test_rerank_disabled_policy_is_visible(self) -> None:
        policy = RankingPolicy(
            policy_id="ranking.no_rerank",
            policy_version="08.1",
            component_weights={
                COMPONENT_RETRIEVAL_RAW_SCORE: 0.45,
                COMPONENT_EVIDENCE_COUNT: 0.20,
                "term_coverage": 0.25,
                "source_determinism": 0.10,
            },
            tie_break_rules=default_ranking_policy().tie_break_rules,
            rerank_enabled=False,
        )
        ranked = rank_evidence(
            RankingRequest(query_terms=("compute_price",), enable_rerank=True),
            self._retrieval_outcome(),
            RankingContext(policy=policy),
        )
        self.assertTrue(any(item.code == "rerank_disabled_by_policy" for item in ranked.diagnostics))

    def test_default_policy_disables_rerank(self) -> None:
        policy = default_ranking_policy()
        self.assertFalse(policy.rerank_enabled)

    def test_explicit_rerank_policy_enables_rerank(self) -> None:
        policy = rerank_ranking_policy()
        self.assertTrue(policy.rerank_enabled)

    def test_tie_break_decision_contains_group_context(self) -> None:
        ranked = rank_evidence(
            RankingRequest(query_terms=("compute_price",), enable_rerank=False),
            self._retrieval_outcome(),
            RankingContext(policy=default_ranking_policy()),
        )
        self.assertTrue(ranked.tie_break_decisions)
        for item in ranked.tie_break_decisions:
            self.assertGreaterEqual(item.tie_group_size, 2)
            self.assertIsNotNone(item.tie_group_rank)

    def test_policy_validation_requires_rerank_component_when_enabled(self) -> None:
        with self.assertRaises(ValueError):
            RankingPolicy(
                policy_id="ranking.invalid",
                policy_version="08.1",
                component_weights={
                    COMPONENT_RETRIEVAL_RAW_SCORE: 0.45,
                    COMPONENT_EVIDENCE_COUNT: 0.20,
                    "term_coverage": 0.25,
                    "source_determinism": 0.10,
                },
                tie_break_rules=("score_total",),
                rerank_enabled=True,
            )

    def test_candidate_status_partial_when_candidate_has_no_evidence(self) -> None:
        retrieval_outcome = self._retrieval_outcome()
        candidate_without_evidence = RetrievalCandidate(
            path_or_url="/repo/without.py",
            locator="/repo/without.py",
            locator_kind="path",
            source_type="repo",
            source_origin="repo-index",
            retrieval_source="repo_scan",
            retrieval_signals=("keyword:compute_price",),
            raw_retrieval_score=0.5,
            merged_source_types=("repo",),
            merged_source_origins=("repo-index",),
            merged_retrieval_sources=("repo_scan",),
        )
        augmented = RetrievalOutcome(
            retrieval_contract_version=retrieval_outcome.retrieval_contract_version,
            candidates=retrieval_outcome.candidates + (candidate_without_evidence,),
            evidence_items=retrieval_outcome.evidence_items,
            retrieval_diagnostics=retrieval_outcome.retrieval_diagnostics,
            source_usage=retrieval_outcome.source_usage,
            status=retrieval_outcome.status,
        )
        ranked = rank_evidence(
            RankingRequest(query_terms=("compute_price",), enable_rerank=False),
            augmented,
            RankingContext(policy=default_ranking_policy()),
        )
        partial_candidates = [item for item in ranked.candidates if item.locator == "/repo/without.py"]
        self.assertEqual(len(partial_candidates), 1)
        self.assertEqual(partial_candidates[0].status, "partial")


if __name__ == "__main__":
    unittest.main()

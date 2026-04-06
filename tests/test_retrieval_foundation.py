from __future__ import annotations

import unittest

from core.retrieval_foundation import (
    BudgetView,
    PolicyContext,
    QueryTermSignal,
    RetrievalContext,
    RetrievalRequest,
    RetrievalSourceAdapter,
    SourceDocument,
    run_retrieval,
)


class RetrievalFoundationTests(unittest.TestCase):
    def _base_sources(self) -> tuple[RetrievalSourceAdapter, ...]:
        repo_source = RetrievalSourceAdapter(
            source_type="repo",
            source_origin="repo-index",
            retrieval_source="repo_scan",
            nondeterministic=False,
            target_scopes=("code", "docs", "general"),
            documents=(
                SourceDocument(
                    path_or_url="/workspace/src/pricing.py",
                    text="def compute_price(value): return value * 2",
                    line_hints={"compute_price": 1},
                ),
                SourceDocument(
                    path_or_url="/workspace/src/shared.py",
                    text="token policy from repo",
                    line_hints={"token": 3},
                ),
            ),
        )
        framework_source = RetrievalSourceAdapter(
            source_type="framework",
            source_origin="framework-docs",
            retrieval_source="framework_adapter",
            nondeterministic=False,
            target_scopes=("code", "docs", "general"),
            documents=(
                SourceDocument(
                    path_or_url="/workspace/src/shared.py",
                    text="token policy from framework",
                    line_hints={"token": 5},
                ),
            ),
        )
        web_source = RetrievalSourceAdapter(
            source_type="web_docs",
            source_origin="docs.example.com",
            retrieval_source="web_adapter",
            nondeterministic=True,
            target_scopes=("docs", "general"),
            documents=(
                SourceDocument(
                    path_or_url="https://docs.example.com/token-policy",
                    text="token policy and compute_price references",
                ),
            ),
        )
        return (repo_source, framework_source, web_source)

    def _request(
        self,
        *,
        source_scope: str = "all",
        max_candidates: int = 50,
        max_evidence_items: int = 200,
        max_external_calls: int = 1,
        allow_nondeterministic_sources: bool = True,
    ) -> RetrievalRequest:
        return RetrievalRequest(
            query_terms=(
                QueryTermSignal(term="compute_price", signal_type="symbol", weight=1.0),
                QueryTermSignal(term="token", signal_type="keyword", weight=0.8),
            ),
            target_scope="code",
            source_scope=source_scope,  # type: ignore[arg-type]
            budget_view=BudgetView(
                max_candidates=max_candidates,
                max_evidence_items=max_evidence_items,
                max_external_calls=max_external_calls,
            ),
            policy_context=PolicyContext(
                allowed_source_types=("repo", "framework", "web_docs", "web_general", "external"),
                allow_nondeterministic_sources=allow_nondeterministic_sources,
            ),
        )

    def test_structured_request_and_outcome(self) -> None:
        context = RetrievalContext(
            sources=self._base_sources(),
            workspace_snapshot_id="ws-1",
            run_id="run-1",
            trace_id="trace-1",
        )
        outcome = run_retrieval(self._request(), context)
        self.assertEqual(outcome.status, "ok")
        self.assertEqual(outcome.workspace_snapshot_id, "ws-1")
        self.assertTrue(outcome.candidates)
        self.assertTrue(outcome.evidence_items)
        self.assertEqual(len(outcome.source_usage), len(context.sources))

    def test_candidate_and_evidence_provenance(self) -> None:
        context = RetrievalContext(sources=self._base_sources())
        outcome = run_retrieval(self._request(), context)
        candidate = outcome.candidates[0]
        evidence = outcome.evidence_items[0]
        self.assertTrue(candidate.path_or_url)
        self.assertTrue(candidate.source_origin)
        self.assertTrue(candidate.retrieval_source)
        self.assertTrue(candidate.retrieval_signals)
        self.assertTrue(evidence.path_or_url)
        self.assertTrue(evidence.retrieval_source)
        self.assertTrue(evidence.source_type in ("repo", "framework", "web_docs"))

    def test_deduplication_preserves_provenance(self) -> None:
        context = RetrievalContext(sources=self._base_sources())
        outcome = run_retrieval(self._request(), context)
        shared_candidates = [item for item in outcome.candidates if item.locator.endswith("/workspace/src/shared.py")]
        self.assertEqual(len(shared_candidates), 1)
        shared = shared_candidates[0]
        self.assertIn("repo", shared.merged_source_types)
        self.assertIn("framework", shared.merged_source_types)
        self.assertTrue(any(d.code == "candidate_deduplicated" for d in outcome.retrieval_diagnostics))

    def test_status_partial_due_to_budget(self) -> None:
        context = RetrievalContext(sources=self._base_sources())
        outcome = run_retrieval(
            self._request(max_candidates=1, max_evidence_items=0),
            context,
        )
        self.assertEqual(outcome.status, "partial")
        self.assertEqual(len(outcome.candidates), 1)
        self.assertEqual(len(outcome.evidence_items), 0)
        candidate_locators = {item.locator for item in outcome.candidates}
        evidence_locators = {item.locator for item in outcome.evidence_items}
        self.assertTrue(evidence_locators.issubset(candidate_locators))

    def test_status_blocked_due_to_policy(self) -> None:
        context = RetrievalContext(sources=self._base_sources())
        request = RetrievalRequest(
            query_terms=(QueryTermSignal(term="token", signal_type="keyword"),),
            target_scope="code",
            source_scope="all",
            budget_view=BudgetView(max_candidates=10, max_evidence_items=10, max_external_calls=0),
            policy_context=PolicyContext(
                allowed_source_types=("web_docs",),
                allow_nondeterministic_sources=False,
            ),
        )
        outcome = run_retrieval(request, context)
        self.assertEqual(outcome.status, "blocked")
        self.assertTrue(any(d.code in ("source_blocked_by_policy", "nondeterministic_source_blocked") for d in outcome.retrieval_diagnostics))
        self.assertTrue(any(item.selection_status == "blocked_policy" for item in outcome.source_usage))

    def test_status_error_when_query_terms_missing(self) -> None:
        context = RetrievalContext(sources=self._base_sources())
        request = RetrievalRequest(
            query_terms=tuple(),
            target_scope="code",
            source_scope="all",
            budget_view=BudgetView(),
            policy_context=PolicyContext(),
        )
        outcome = run_retrieval(request, context)
        self.assertEqual(outcome.status, "error")
        self.assertTrue(any(d.code == "request_missing_query_terms" for d in outcome.retrieval_diagnostics))

    def test_nondeterministic_source_marking(self) -> None:
        context = RetrievalContext(sources=self._base_sources())
        request = RetrievalRequest(
            query_terms=(QueryTermSignal(term="token", signal_type="keyword"),),
            target_scope="docs",
            source_scope="all",
            budget_view=BudgetView(max_candidates=20, max_evidence_items=20, max_external_calls=1),
            policy_context=PolicyContext(
                allowed_source_types=("repo", "framework", "web_docs"),
                allow_nondeterministic_sources=True,
            ),
        )
        outcome = run_retrieval(request, context)
        self.assertTrue(any(d.code == "nondeterministic_source_used" for d in outcome.retrieval_diagnostics))
        self.assertTrue(any(u.nondeterministic for u in outcome.source_usage if u.used))

    def test_source_usage_contains_out_of_scope_and_out_of_target_entries(self) -> None:
        sources = self._base_sources() + (
            RetrievalSourceAdapter(
                source_type="external",
                source_origin="external-api",
                retrieval_source="external_adapter",
                nondeterministic=False,
                target_scopes=("general",),
                documents=(SourceDocument(path_or_url="https://api.example.com/item", text="token"),),
            ),
        )
        context = RetrievalContext(sources=sources)
        request = RetrievalRequest(
            query_terms=(QueryTermSignal(term="token", signal_type="keyword"),),
            target_scope="docs",
            source_scope="framework_only",
            budget_view=BudgetView(max_candidates=20, max_evidence_items=20, max_external_calls=0),
            policy_context=PolicyContext(
                allowed_source_types=("repo", "framework", "web_docs", "web_general", "external"),
                allow_nondeterministic_sources=True,
            ),
        )
        outcome = run_retrieval(request, context)
        statuses = {item.selection_status for item in outcome.source_usage}
        self.assertIn("out_of_scope", statuses)
        self.assertIn("out_of_target", statuses)

    def test_no_selected_sources_status_partial_for_scope_or_target_mismatch(self) -> None:
        context = RetrievalContext(
            sources=(
                RetrievalSourceAdapter(
                    source_type="repo",
                    source_origin="repo-index",
                    retrieval_source="repo_scan",
                    nondeterministic=False,
                    target_scopes=("code",),
                    documents=(SourceDocument(path_or_url="/workspace/src/x.py", text="x"),),
                ),
            )
        )
        request = RetrievalRequest(
            query_terms=(QueryTermSignal(term="x", signal_type="keyword"),),
            target_scope="docs",
            source_scope="all",
            budget_view=BudgetView(max_candidates=10, max_evidence_items=10, max_external_calls=0),
            policy_context=PolicyContext(),
        )
        outcome = run_retrieval(request, context)
        self.assertEqual(outcome.status, "partial")
        self.assertTrue(any(item.selection_status == "out_of_target" for item in outcome.source_usage))

    def test_query_term_signal_type_validation(self) -> None:
        with self.assertRaises(ValueError):
            QueryTermSignal(term="x", signal_type="freeform")

    def test_budget_truncation_diagnostics_are_consistent(self) -> None:
        context = RetrievalContext(sources=self._base_sources())
        outcome = run_retrieval(
            self._request(max_candidates=1, max_evidence_items=0),
            context,
        )
        codes = {item.code for item in outcome.retrieval_diagnostics}
        self.assertIn("candidate_budget_limited", codes)
        self.assertIn("budget_truncation_applied", codes)
        self.assertIn("evidence_filtered_for_candidate_budget", codes)
        self.assertIn("candidates_without_evidence_after_budget", codes)
        candidate_locators = {item.locator for item in outcome.candidates}
        evidence_locators = {item.locator for item in outcome.evidence_items}
        self.assertTrue(evidence_locators.issubset(candidate_locators))

    def test_evidence_uses_snippet_not_full_document_text(self) -> None:
        long_doc = "header line\n" + "\n".join(f"line {idx} filler text" for idx in range(2, 30)) + "\ncompute_price target line\ntail"
        source = RetrievalSourceAdapter(
            source_type="repo",
            source_origin="repo-index",
            retrieval_source="repo_scan",
            nondeterministic=False,
            target_scopes=("code",),
            documents=(
                SourceDocument(
                    path_or_url="/workspace/src/long.py",
                    text=long_doc,
                    line_hints={"compute_price": 30},
                ),
            ),
        )
        context = RetrievalContext(sources=(source,))
        request = RetrievalRequest(
            query_terms=(QueryTermSignal(term="compute_price", signal_type="symbol"),),
            target_scope="code",
            source_scope="all",
            budget_view=BudgetView(max_candidates=10, max_evidence_items=10, max_external_calls=0),
            policy_context=PolicyContext(),
        )
        outcome = run_retrieval(request, context)
        self.assertTrue(outcome.evidence_items)
        snippet = outcome.evidence_items[0].text
        self.assertIn("compute_price", snippet)
        self.assertLess(len(snippet), len(long_doc))

    def test_retrieval_diagnostics_include_structured_context(self) -> None:
        context = RetrievalContext(sources=self._base_sources())
        request = RetrievalRequest(
            query_terms=(QueryTermSignal(term="token", signal_type="keyword"),),
            target_scope="code",
            source_scope="all",
            budget_view=BudgetView(max_candidates=0, max_evidence_items=1, max_external_calls=0),
            policy_context=PolicyContext(
                allowed_source_types=("repo",),
                allow_nondeterministic_sources=False,
            ),
        )
        outcome = run_retrieval(request, context)
        contextful = [item for item in outcome.retrieval_diagnostics if item.context is not None]
        self.assertTrue(contextful)
        self.assertTrue(any(item.code == "source_blocked_by_policy" and "selection_status" in (item.context or {}) for item in contextful))
        self.assertTrue(any(item.code == "budget_truncation_applied" and "candidates_before" in (item.context or {}) for item in contextful))

    def test_deterministic_behavior_for_equal_input(self) -> None:
        context = RetrievalContext(sources=self._base_sources(), workspace_snapshot_id="ws-x")
        request = self._request()
        first = run_retrieval(request, context)
        second = run_retrieval(request, context)
        self.assertEqual(first.status, second.status)
        self.assertEqual(first.candidates, second.candidates)
        self.assertEqual(first.evidence_items, second.evidence_items)
        self.assertEqual(first.retrieval_diagnostics, second.retrieval_diagnostics)


if __name__ == "__main__":
    unittest.main()

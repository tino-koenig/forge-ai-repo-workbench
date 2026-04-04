"""Canonical init template and option registry."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InitTemplate:
    template_id: str
    description: str
    planner_mode: str
    orchestrator_mode: str
    index_enrichment_enabled: bool
    output_language: str
    review_strictness: str


INIT_TEMPLATES: dict[str, InitTemplate] = {
    "balanced": InitTemplate(
        template_id="balanced",
        description="Recommended default for most teams (planner/orchestrator optional).",
        planner_mode="optional",
        orchestrator_mode="optional",
        index_enrichment_enabled=True,
        output_language="auto",
        review_strictness="balanced",
    ),
    "strict-review": InitTemplate(
        template_id="strict-review",
        description="Stricter review defaults and stronger review baseline rule severity.",
        planner_mode="optional",
        orchestrator_mode="optional",
        index_enrichment_enabled=True,
        output_language="auto",
        review_strictness="strict",
    ),
    "lightweight": InitTemplate(
        template_id="lightweight",
        description="Lower-cost defaults with planner/orchestrator off and minimal enrichment.",
        planner_mode="off",
        orchestrator_mode="off",
        index_enrichment_enabled=False,
        output_language="auto",
        review_strictness="balanced",
    ),
}

INIT_TEMPLATE_CHOICES = tuple(INIT_TEMPLATES.keys())
INIT_OUTPUT_LANGUAGE_CHOICES = ("auto", "de", "en")
INIT_REVIEW_STRICTNESS_CHOICES = ("balanced", "strict")
INIT_INDEX_ENRICHMENT_CHOICES = ("enabled", "disabled")
INIT_SOURCE_SCOPE_CHOICES = ("repo_only", "all")
INIT_SOURCE_SCOPE_DEFAULT = "repo_only"

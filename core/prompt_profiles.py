"""Prompt profile registry and capability mapping policy."""

from __future__ import annotations

from pathlib import Path

from core.capability_model import Capability


PROFILE_TEMPLATE = {
    "strict_read_only": "default_read_only.txt",
    "review_strict": "review_strict.txt",
    "describe_onboarding": "describe_onboarding.txt",
}

ALLOWED_PROMPT_PROFILES = set(PROFILE_TEMPLATE.keys())

CAPABILITY_DEFAULT_PROMPT_PROFILE = {
    Capability.INIT: "strict_read_only",
    Capability.QUERY: "strict_read_only",
    Capability.EXPLAIN: "strict_read_only",
    Capability.REVIEW: "review_strict",
    Capability.DESCRIBE: "describe_onboarding",
    Capability.TEST: "strict_read_only",
    Capability.DOCTOR: "strict_read_only",
    Capability.INDEX: "strict_read_only",
    Capability.RUNS: "strict_read_only",
}

CAPABILITY_ALLOWED_PROMPT_PROFILES = {
    Capability.INIT: {"strict_read_only"},
    Capability.QUERY: {"strict_read_only"},
    Capability.EXPLAIN: {"strict_read_only"},
    Capability.REVIEW: {"strict_read_only", "review_strict"},
    Capability.DESCRIBE: {"strict_read_only", "describe_onboarding"},
    Capability.TEST: {"strict_read_only"},
    Capability.DOCTOR: {"strict_read_only"},
    Capability.INDEX: {"strict_read_only"},
    Capability.RUNS: {"strict_read_only"},
}


def default_prompt_profile(capability: Capability) -> str:
    return CAPABILITY_DEFAULT_PROMPT_PROFILE[capability]


def is_prompt_profile_allowed(capability: Capability, profile: str) -> bool:
    return profile in CAPABILITY_ALLOWED_PROMPT_PROFILES[capability]


def default_system_template_path(profile: str) -> Path:
    filename = PROFILE_TEMPLATE[profile]
    return Path(__file__).resolve().parents[1] / "prompts" / "system" / filename

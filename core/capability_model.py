"""Canonical command model for Forge capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Capability(str, Enum):
    QUERY = "query"
    EXPLAIN = "explain"
    REVIEW = "review"
    DESCRIBE = "describe"
    TEST = "test"
    INDEX = "index"


class Profile(str, Enum):
    SIMPLE = "simple"
    STANDARD = "standard"
    DETAILED = "detailed"


class EffectClass(str, Enum):
    READ_ONLY = "read_only"
    FORGE_WRITE = "forge_write"
    REPO_WRITE = "repo_write"
    COMMAND_EXEC = "command_exec"


@dataclass(frozen=True)
class CapabilityPolicy:
    allowed_effects: frozenset[EffectClass]


@dataclass(frozen=True)
class CommandRequest:
    capability: Capability
    profile: Profile
    payload: str


class EffectViolationError(PermissionError):
    """Raised when a capability tries to use a disallowed effect."""


CAPABILITY_POLICIES: dict[Capability, CapabilityPolicy] = {
    Capability.QUERY: CapabilityPolicy(allowed_effects=frozenset({EffectClass.READ_ONLY})),
    Capability.EXPLAIN: CapabilityPolicy(allowed_effects=frozenset({EffectClass.READ_ONLY})),
    Capability.REVIEW: CapabilityPolicy(allowed_effects=frozenset({EffectClass.READ_ONLY})),
    Capability.DESCRIBE: CapabilityPolicy(allowed_effects=frozenset({EffectClass.READ_ONLY})),
    Capability.TEST: CapabilityPolicy(allowed_effects=frozenset({EffectClass.READ_ONLY})),
    Capability.INDEX: CapabilityPolicy(
        allowed_effects=frozenset({EffectClass.READ_ONLY, EffectClass.FORGE_WRITE})
    ),
}


def parse_profile_and_payload(parts: list[str]) -> tuple[Profile, str]:
    """Parse optional profile prefix from positional parts."""
    if not parts:
        return Profile.STANDARD, ""

    first = parts[0]
    if first in {Profile.SIMPLE.value, Profile.STANDARD.value, Profile.DETAILED.value}:
        return Profile(first), " ".join(parts[1:]).strip()

    return Profile.STANDARD, " ".join(parts).strip()


def build_request(
    capability_name: str,
    parts: list[str],
    *,
    require_payload: bool,
) -> CommandRequest:
    capability = Capability(capability_name)
    profile, payload = parse_profile_and_payload(parts)
    if require_payload and not payload:
        raise ValueError(
            f"Capability '{capability.value}' requires a target/question; "
            "optionally prefix with simple|standard|detailed."
        )
    return CommandRequest(capability=capability, profile=profile, payload=payload)

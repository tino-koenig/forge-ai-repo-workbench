"""Effect enforcement for capability execution."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.capability_model import (
    CAPABILITY_POLICIES,
    CommandRequest,
    EffectClass,
    EffectViolationError,
)


@dataclass
class ExecutionSession:
    request: CommandRequest
    effective_effects: set[EffectClass] = field(default_factory=set)

    def record_effect(self, effect: EffectClass, detail: str = "") -> None:
        policy = CAPABILITY_POLICIES[self.request.capability]
        if effect not in policy.allowed_effects:
            message = (
                f"Disallowed effect '{effect.value}' for capability "
                f"'{self.request.capability.value}'."
            )
            if detail:
                message = f"{message} Detail: {detail}"
            raise EffectViolationError(message)
        self.effective_effects.add(effect)

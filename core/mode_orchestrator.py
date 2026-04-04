"""Central bounded orchestration loop utilities reusable across modes."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Iterator


@dataclass(frozen=True)
class OrchestrationCycle:
    iteration: int
    elapsed_ms: int
    wall_time_exhausted: bool


def iter_bounded_cycles(
    *,
    max_iterations: int,
    max_wall_time_ms: int,
) -> Iterator[OrchestrationCycle]:
    """Yield bounded orchestration cycles with shared wall-time accounting."""
    started = time.perf_counter()
    for iteration in range(1, max_iterations + 1):
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if elapsed_ms > max_wall_time_ms:
            yield OrchestrationCycle(
                iteration=iteration,
                elapsed_ms=elapsed_ms,
                wall_time_exhausted=True,
            )
            return
        yield OrchestrationCycle(
            iteration=iteration,
            elapsed_ms=elapsed_ms,
            wall_time_exhausted=False,
        )

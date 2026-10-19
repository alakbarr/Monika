"""
Harness domain package.
Defines core abstractions for the agent harness surface, components, and safety invariants.
"""

from monika.domain.harness.models import (
    ComponentType,
    HarnessComponent,
    HarnessDiff,
    HarnessViolationError,
    SurfaceSpec,
)

__all__ = [
    "ComponentType",
    "HarnessComponent",
    "HarnessDiff",
    "HarnessViolationError",
    "SurfaceSpec",
]

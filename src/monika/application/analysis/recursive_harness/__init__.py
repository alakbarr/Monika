"""
Monika Harness Package (Recursive Agent Harnessing).

Adapts Google Research's Harness^2 principles to algorithmic trading:
- 8-Component modular harness surface (c1..c8).
- Mechanical Fortress invariance (RiskGate & broker immutability).
- Task-Level Recursion: Propose -> Probe -> Contrastive Select -> Compose.
- Harnessing-Level Recursion: Domain Experience Library.
"""

from monika.domain.harness.models import (
    ComponentType,
    HarnessComponent,
    HarnessDiff,
    HarnessViolationError,
    SurfaceSpec,
)
from monika.application.analysis.recursive_harness.composer import CompositionResult, HarnessComposer
from monika.application.analysis.recursive_harness.library import (
    DomainExperienceEntry,
    DomainExperienceLibrary,
    sanitize_domain_slug,
)
from monika.application.analysis.recursive_harness.prober import (
    HarnessProber,
    ProbeMetrics,
    ProbeResult,
    ScenarioBasedProbeRunner,
)
from monika.application.analysis.recursive_harness.proposer import CandidateProposal, HarnessProposer
from monika.application.analysis.recursive_harness.selector import (
    ContrastiveSelection,
    ContrastiveSelector,
)
from monika.application.analysis.recursive_harness.service import (
    RecursionCycleResult,
    RecursiveHarnessService,
)
from monika.application.analysis.recursive_harness.surface import (
    MONIKA_SURFACE,
    classify_component,
    is_path_reserved,
    normalize_rel_path,
    validate_tree_invariants,
)
from monika.application.analysis.recursive_harness.tree import HarnessTree

__all__ = [
    # Domain
    "ComponentType",
    "HarnessComponent",
    "HarnessDiff",
    "HarnessViolationError",
    "SurfaceSpec",
    # Surface & Tree
    "MONIKA_SURFACE",
    "HarnessTree",
    "classify_component",
    "is_path_reserved",
    "normalize_rel_path",
    "validate_tree_invariants",
    # Library
    "DomainExperienceEntry",
    "DomainExperienceLibrary",
    "sanitize_domain_slug",
    # Task-Level Recursion
    "CandidateProposal",
    "HarnessProposer",
    "ProbeMetrics",
    "ProbeResult",
    "HarnessProber",
    "ScenarioBasedProbeRunner",
    "ContrastiveSelection",
    "ContrastiveSelector",
    "CompositionResult",
    "HarnessComposer",
    # Unified Service
    "RecursionCycleResult",
    "RecursiveHarnessService",
]

"""
Recursive Harness Service for Monika.

Unified facade orchestrating:
1. Task-Level Recursion: Propose -> Probe -> Contrastive Select -> Compose.
2. Harnessing-Level Recursion: Reflect & Record Domain Experience into Persistent Library.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from monika.domain.harness.models import SurfaceSpec
from monika.application.analysis.recursive_harness.composer import CompositionResult, HarnessComposer
from monika.application.analysis.recursive_harness.library import DomainExperienceLibrary
from monika.application.analysis.recursive_harness.prober import HarnessProber
from monika.application.analysis.recursive_harness.proposer import HarnessProposer
from monika.application.analysis.recursive_harness.selector import ContrastiveSelection, ContrastiveSelector
from monika.application.analysis.recursive_harness.surface import MONIKA_SURFACE
from monika.application.analysis.recursive_harness.tree import HarnessTree

logger = logging.getLogger("TradingAgent.RecursiveHarnessService")


@dataclass(frozen=True)
class RecursionCycleResult:
    """The complete result of an autonomous recursive harnessing cycle."""

    run_id: str
    domain: str
    final_tree: HarnessTree
    selection: ContrastiveSelection
    composition: CompositionResult
    experience_recorded: bool
    summary: str


class RecursiveHarnessService:
    """
    Main entry point for recursive agent self-improvement in Monika.
    """

    def __init__(
        self,
        library: Optional[DomainExperienceLibrary] = None,
        proposer: Optional[HarnessProposer] = None,
        prober: Optional[HarnessProber] = None,
        selector: Optional[ContrastiveSelector] = None,
        composer: Optional[HarnessComposer] = None,
        spec: SurfaceSpec = MONIKA_SURFACE,
    ):
        self.spec = spec
        self.library = library or DomainExperienceLibrary(spec=spec)
        self.proposer = proposer or HarnessProposer(spec=spec)
        self.prober = prober or HarnessProber()
        self.selector = selector or ContrastiveSelector()
        self.composer = composer or HarnessComposer(spec=spec)

    def run_recursion_cycle(
        self,
        domain: str,
        base_tree: Optional[HarnessTree] = None,
        scenario_data: Optional[Mapping[str, Any]] = None,
        run_id: Optional[str] = None,
        k_candidates: int = 2,
    ) -> RecursionCycleResult:
        """
        Executes a full two-level recursive harnessing cycle for the given market domain.
        """
        cycle_id = run_id or f"cycle_{uuid.uuid4().hex[:10]}"
        scen_data = scenario_data or {"domain": domain, "mode": "simulation"}

        # 1. Resolve base tree (prioritize latest adopted harness in library, or baseline)
        if base_tree is None:
            latest = self.library.get_latest_harness(domain)
            base = latest if latest is not None else HarnessTree.build_baseline_tree(spec=self.spec)
        else:
            base = base_tree

        # 2. Query historical lessons from domain experience library
        prior_lessons = self.library.format_domain_lessons_for_prompt(domain, max_lessons=3)

        # 3. Task-Level Phase 1: Propose candidate variations
        candidates = self.proposer.propose_candidates(
            base_tree=base,
            domain=domain,
            regime_context=scen_data,
            historical_lessons=prior_lessons,
            k_candidates=k_candidates,
        )

        # 4. Task-Level Phase 2: Probe candidates against simulation
        probe_results = self.prober.probe_candidates(
            base_tree=base,
            candidates=candidates,
            scenario_data=scen_data,
        )

        # 5. Task-Level Phase 3: Contrastive Selection
        selection = self.selector.select(
            domain=domain,
            probe_results=probe_results,
            regime_context=scen_data,
        )

        # 6. Task-Level Phase 4: Compose accepted edits
        composition = self.composer.compose(base_tree=base, selection=selection)

        # 7. Harnessing-Level: Reflect & record adopted experience into library
        exp_recorded = False
        if composition.was_modified:
            self.library.record_experience(
                domain=domain,
                run_id=cycle_id,
                tree=composition.final_tree,
                cue=selection.experience_cue,
                lesson=selection.experience_lesson,
                evidence=selection.evidence,
            )
            exp_recorded = True

        summary = (
            f"Recursive cycle [{cycle_id}] for domain '{domain}': "
            f"Chosen: '{selection.chosen_candidate_id}' (base={selection.chosen_is_base}). "
            f"Score: {selection.composite_score:.3f}. Modified: {composition.was_modified}."
        )
        logger.info(f"[RecursiveHarnessService] {summary}")

        return RecursionCycleResult(
            run_id=cycle_id,
            domain=domain,
            final_tree=composition.final_tree,
            selection=selection,
            composition=composition,
            experience_recorded=exp_recorded,
            summary=summary,
        )

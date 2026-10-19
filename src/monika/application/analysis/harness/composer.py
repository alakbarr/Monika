"""
Harness Composer for Monika (Task-Level Recursion - Phase 4: Compose).

Safely merges accepted candidate improvements into the active harness tree,
ensuring atomic application and full invariant preservation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from monika.domain.harness.models import HarnessDiff, HarnessViolationError, SurfaceSpec
from monika.application.analysis.harness.selector import ContrastiveSelection
from monika.application.analysis.harness.surface import MONIKA_SURFACE, is_path_reserved
from monika.application.analysis.harness.tree import HarnessTree

logger = logging.getLogger("TradingAgent.HarnessComposer")


@dataclass(frozen=True)
class CompositionResult:
    """The result of composing a selected harness into production."""

    final_tree: HarnessTree
    diff_applied: HarnessDiff
    was_modified: bool
    summary: str


class HarnessComposer:
    """
    Composes selected candidate diffs onto the base harness tree safely.
    """

    def __init__(self, spec: SurfaceSpec = MONIKA_SURFACE):
        self.spec = spec

    def compose(
        self,
        base_tree: HarnessTree,
        selection: ContrastiveSelection,
    ) -> CompositionResult:
        """
        Atomically applies accepted candidate diffs.
        If selection kept base, returns unmodified tree with empty diff.
        """
        if selection.chosen_is_base:
            return CompositionResult(
                final_tree=base_tree,
                diff_applied=HarnessDiff(),
                was_modified=False,
                summary="Base harness retained; no changes applied.",
            )

        candidate_tree = selection.chosen_tree
        diff = base_tree.diff(candidate_tree)

        # Invariant check: Ensure no modified or added paths touch reserved zones
        for path in set(diff.added.keys()) | set(diff.modified.keys()) | set(diff.removed):
            if is_path_reserved(path, self.spec):
                raise HarnessViolationError(f"Composition blocked: Candidate diff touches reserved path '{path}'.")

        # Apply diff safely
        composed_tree = base_tree.apply_diff(diff)
        summary = (
            f"Composed candidate '{selection.chosen_candidate_id}' into harness: "
            f"+{len(diff.added)} added, ~{len(diff.modified)} modified, -{len(diff.removed)} removed."
        )
        logger.info(f"[HarnessComposer] {summary}")

        return CompositionResult(
            final_tree=composed_tree,
            diff_applied=diff,
            was_modified=True,
            summary=summary,
        )

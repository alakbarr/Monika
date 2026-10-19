"""
HarnessTree representation, diffing, validation, and file persistence for Monika.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

from monika.domain.harness.models import (
    ComponentType,
    HarnessComponent,
    HarnessDiff,
    HarnessViolationError,
    SurfaceSpec,
)
from monika.application.analysis.harness.surface import (
    MONIKA_SURFACE,
    classify_component,
    normalize_rel_path,
    validate_tree_invariants,
)


@dataclass
class HarnessTree:
    """
    A validated, immutable-in-memory snapshot of Monika's 8-component harness.
    """

    components: dict[str, HarnessComponent] = field(default_factory=dict)
    spec: SurfaceSpec = field(default=MONIKA_SURFACE)

    def to_dict(self) -> dict[str, str]:
        """Returns rel_path -> text content."""
        return {p: comp.content for p, comp in self.components.items()}

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, str],
        spec: SurfaceSpec = MONIKA_SURFACE,
    ) -> HarnessTree:
        """
        Builds and validates a HarnessTree from a dict of relative paths and contents.
        """
        validate_tree_invariants(data, spec)
        components: dict[str, HarnessComponent] = {}
        for path, content in data.items():
            norm = normalize_rel_path(path)
            comp_type = classify_component(norm, spec)
            components[norm] = HarnessComponent(
                rel_path=norm,
                component_type=comp_type,
                content=content,
            )
        return cls(components=components, spec=spec)

    def diff(self, other: HarnessTree) -> HarnessDiff:
        """
        Calculates the structured diff between this tree and another.
        """
        added: dict[str, str] = {}
        modified: dict[str, str] = {}
        removed: list[str] = []

        my_dict = self.to_dict()
        other_dict = other.to_dict()

        for path, content in other_dict.items():
            if path not in my_dict:
                added[path] = content
            elif my_dict[path] != content:
                modified[path] = content

        for path in my_dict:
            if path not in other_dict:
                removed.append(path)

        return HarnessDiff(
            added=added,
            modified=modified,
            removed=tuple(sorted(removed)),
        )

    def apply_diff(self, diff: HarnessDiff) -> HarnessTree:
        """
        Applies a validated diff, producing a new validated HarnessTree.
        """
        curr = dict(self.to_dict())

        # Process removals
        for path in diff.removed:
            norm = normalize_rel_path(path)
            curr.pop(norm, None)

        # Process modifications and additions
        for path, content in diff.modified.items():
            norm = normalize_rel_path(path)
            curr[norm] = content

        for path, content in diff.added.items():
            norm = normalize_rel_path(path)
            curr[norm] = content

        return HarnessTree.from_dict(curr, self.spec)

    def text_diff(self, other: HarnessTree) -> str:
        """Generates unified git-style text diff for observability."""
        lines: list[str] = []
        my_dict = self.to_dict()
        other_dict = other.to_dict()
        all_paths = sorted(set(my_dict.keys()) | set(other_dict.keys()))

        for p in all_paths:
            content_a = my_dict.get(p, "").splitlines(keepends=True)
            content_b = other_dict.get(p, "").splitlines(keepends=True)
            if content_a != content_b:
                diff_lines = list(
                    difflib.unified_diff(
                        content_a,
                        content_b,
                        fromfile=f"a/{p}",
                        tofile=f"b/{p}",
                    )
                )
                lines.extend(diff_lines)

        return "".join(lines)

    def export_to_directory(self, target_dir: Path | str) -> None:
        """Exports all components to disk under target_dir."""
        dest = Path(target_dir).resolve()
        dest.mkdir(parents=True, exist_ok=True)
        for rel_path, comp in self.components.items():
            file_path = dest / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(comp.content, encoding="utf-8")

    @classmethod
    def load_from_directory(cls, source_dir: Path | str, spec: SurfaceSpec = MONIKA_SURFACE) -> HarnessTree:
        """
        Scans a directory for surface files, assembling a validated HarnessTree.
        """
        src = Path(source_dir).resolve()
        if not src.is_dir():
            raise HarnessViolationError(f"Directory not found: {src}")

        raw_dict: dict[str, str] = {}
        for file_path in sorted(src.rglob("*")):
            if not file_path.is_file() or "__pycache__" in file_path.parts:
                continue
            rel = str(file_path.relative_to(src)).replace("\\", "/")
            try:
                # Classifies and ensures it is on the surface
                classify_component(rel, spec)
                raw_dict[rel] = file_path.read_text(encoding="utf-8", errors="replace")
            except HarnessViolationError:
                # Silently ignore non-surface files during general directory scan
                continue

        return cls.from_dict(raw_dict, spec)

    @classmethod
    def build_baseline_tree(
        cls,
        system_prompt: Optional[str] = None,
        guardrails: Optional[str] = None,
        memory: Optional[str] = None,
        tool_guidance: Optional[str] = None,
        spec: SurfaceSpec = MONIKA_SURFACE,
    ) -> HarnessTree:
        """
        Constructs a standard baseline tree for Monika with production defaults.
        """
        sp = system_prompt or (
            "# Monika Trading Intelligence System\n"
            "Role: Quantitative market analyst and structured trade hypothesis formulator.\n"
            "Discipline: Reason rigorously using verifiable market structure, macro liquidity, and multi-timeframe orderflow.\n"
        )
        gr = guardrails or (
            "# Monika Reasoning Guardrails\n"
            "1. AI proposes, the Mechanical Fortress disposes: Never attempt broker execution directly.\n"
            "2. Fail closed: Reject setups on missing, stale, or conflicting indicators.\n"
            "3. Grounding: All cited prices and levels must be anchored in verified market snapshots.\n"
        )
        mem = memory or (
            "# Long-Term Market Memory & Epistemic Ledger\n"
            "Tracks market regime transitions, cross-asset contagion, and consolidated alpha lessons.\n"
        )
        tg = tool_guidance or (
            "# Tool Guidance for Quantitative Analysis\n"
            "Query indicators, orderbook liquidity, and statistical simulations within budget.\n"
        )

        data = {
            "systemprompt.md": sp,
            "guardrails.md": gr,
            "LongTermMEMORY.md": mem,
            "tool_guidance.md": tg,
        }
        return cls.from_dict(data, spec)

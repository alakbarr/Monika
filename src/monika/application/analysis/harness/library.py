"""
Domain Experience Library for Monika (Harnessing-Level Recursion).

Stores structured lessons, contrastive reflections, and adopted harness snapshots
organized by market domain (Asset Class + Regime), e.g.:
data/harness_library/
  METALS__VOLATILITY_EXPANSION/
    INDEX.md
    harnesses/
      run_20261019_xau_01/
        harness/
          guardrails.md
          skills/volatility_expansion.md
        EXPERIENCE.md
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from monika.domain.harness.models import SurfaceSpec
from monika.application.analysis.harness.surface import MONIKA_SURFACE
from monika.application.analysis.harness.tree import HarnessTree
from monika.infrastructure.infra.paths import get_data_dir

logger = logging.getLogger("TradingAgent.HarnessLibrary")


def sanitize_domain_slug(domain: str) -> str:
    """Normalizes domain identifier (e.g. 'FX / Trending' -> 'FX__TRENDING')."""
    clean = re.sub(r"\s*[/\\|]+\s*", "__", domain.strip().upper())
    clean = re.sub(r"\s+", "_", clean)
    clean = re.sub(r"[^A-Z0-9_\-]", "", clean)
    return clean or "GENERAL__BALANCED"


@dataclass(frozen=True)
class DomainExperienceEntry:
    """A verified empirical lesson stored in the domain library."""

    domain: str
    run_id: str
    timestamp: str
    cue: str
    lesson: str
    evidence: Mapping[str, Any]
    harness_path: Path

    def to_markdown(self) -> str:
        evidence_json = json.dumps(self.evidence, indent=2, sort_keys=True)
        return (
            f"# Experience Record: {self.run_id}\n\n"
            f"- **Domain**: `{self.domain}`\n"
            f"- **Recorded At**: `{self.timestamp}`\n\n"
            f"## Cue (Market Trigger Pattern)\n"
            f"{self.cue.strip()}\n\n"
            f"## Lesson (Causal Mechanism & Contrast)\n"
            f"{self.lesson.strip()}\n\n"
            f"## Empirical Evidence\n"
            f"```json\n{evidence_json}\n```\n"
        )


class DomainExperienceLibrary:
    """
    Manages the persistent store of domain-specific harnesses and contrastive experiences.
    """

    def __init__(
        self,
        root_dir: Optional[Path | str] = None,
        spec: SurfaceSpec = MONIKA_SURFACE,
    ):
        if root_dir is not None:
            self.root = Path(root_dir).resolve()
        else:
            self.root = get_data_dir() / "harness_library"
        self.spec = spec
        self.root.mkdir(parents=True, exist_ok=True)

    def _domain_dir(self, domain: str) -> Path:
        slug = sanitize_domain_slug(domain)
        d = self.root / slug
        d.mkdir(parents=True, exist_ok=True)
        return d

    def record_experience(
        self,
        domain: str,
        run_id: str,
        tree: HarnessTree,
        cue: str,
        lesson: str,
        evidence: Mapping[str, Any],
    ) -> DomainExperienceEntry:
        """
        Stores an adopted harness snapshot and its structured experience markdown.
        """
        d_dir = self._domain_dir(domain)
        slug = sanitize_domain_slug(domain)
        clean_run = re.sub(r"[^a-zA-Z0-9_\-]", "_", run_id.strip())
        entry_dir = d_dir / "harnesses" / clean_run
        harness_dir = entry_dir / "harness"
        entry_dir.mkdir(parents=True, exist_ok=True)

        # 1. Export harness snapshot
        tree.export_to_directory(harness_dir)

        # 2. Write EXPERIENCE.md
        now_iso = datetime.now(timezone.utc).isoformat()
        entry = DomainExperienceEntry(
            domain=slug,
            run_id=clean_run,
            timestamp=now_iso,
            cue=cue,
            lesson=lesson,
            evidence=evidence,
            harness_path=harness_dir,
        )
        exp_file = entry_dir / "EXPERIENCE.md"
        exp_file.write_text(entry.to_markdown(), encoding="utf-8")

        # 3. Update domain INDEX.md
        self._update_index(slug)
        logger.info(f"[HarnessLibrary] Recorded experience for domain '{slug}' run '{clean_run}'")
        return entry

    def _update_index(self, domain_slug: str) -> None:
        d_dir = self.root / domain_slug
        harnesses_dir = d_dir / "harnesses"
        if not harnesses_dir.is_dir():
            return

        entries: list[str] = []
        for run_path in sorted(harnesses_dir.iterdir()):
            if run_path.is_dir() and (run_path / "EXPERIENCE.md").is_file():
                entries.append(run_path.name)

        index_file = d_dir / "INDEX.md"
        content = [
            f"# Domain Experience Index: {domain_slug}\n",
            f"Total adopted harness iterations: {len(entries)}\n",
            "## Adopted Runs\n",
        ]
        for e in entries:
            content.append(f"- [{e}](harnesses/{e}/EXPERIENCE.md)")
        index_file.write_text("\n".join(content) + "\n", encoding="utf-8")

    def list_domains(self) -> list[str]:
        """Lists all registered domain directories."""
        return sorted(p.name for p in self.root.iterdir() if p.is_dir())

    def list_entries(self, domain: str) -> list[str]:
        """Lists all run IDs in a domain."""
        slug = sanitize_domain_slug(domain)
        harnesses_dir = self.root / slug / "harnesses"
        if not harnesses_dir.is_dir():
            return []
        return sorted(p.name for p in harnesses_dir.iterdir() if p.is_dir())

    def get_latest_harness(self, domain: str) -> Optional[HarnessTree]:
        """Loads the most recently adopted harness tree for this domain."""
        entries = self.list_entries(domain)
        if not entries:
            return None
        latest_run = entries[-1]
        slug = sanitize_domain_slug(domain)
        h_dir = self.root / slug / "harnesses" / latest_run / "harness"
        if h_dir.is_dir():
            return HarnessTree.load_from_directory(h_dir, self.spec)
        return None

    def format_domain_lessons_for_prompt(self, domain: str, max_lessons: int = 4) -> str:
        """
        Extracts recent lessons from this domain into a concise markdown section for prompt injection.
        """
        slug = sanitize_domain_slug(domain)
        entries = self.list_entries(slug)
        if not entries:
            return ""

        recent = entries[-max_lessons:]
        lines = [f"### Historical Domain Lessons ({slug}):"]
        for r_id in recent:
            exp_file = self.root / slug / "harnesses" / r_id / "EXPERIENCE.md"
            if exp_file.is_file():
                txt = exp_file.read_text(encoding="utf-8")
                # Extract lesson section
                m = re.search(r"## Lesson.*?\n(.*?)(?=\n##|\Z)", txt, re.S)
                if m:
                    lines.append(f"- **[{r_id}]**: {m.group(1).strip()}")

        return "\n".join(lines) if len(lines) > 1 else ""

from pathlib import Path

from monika.core.paths import get_skills_dir

# ==============================================================================
# File: analysis/memory/progressive_loader.py
# Description: Progressive Disclosure Skill & Playbook Loading Engine (Level 0 - Level 2)
# ==============================================================================

"""
Implements 3-tier Progressive Disclosure for trading playbooks and institutional skills:
- Level 0: Lightweight strategy index (~100 tokens). Injected in system prompt without token bloat.
- Level 1: Target symbol & regime playbook. Loaded only during Stage 2 per-asset analysis.
- Level 2: On-demand tactical reference documents (e.g. Asian session liquidity sweeps, FOMC reaction playbooks).
  Loaded dynamically via tool query when specific market conditions emerge.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TradingAgent.Memory.ProgressiveLoader")


class ProgressivePlaybookLoader:
    """Manages progressive 3-tier loading of trading playbooks."""

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = get_skills_dir() / "trading"

        self.playbooks_dir = self.base_dir / "playbooks"
        self.crystallized_dir = self.base_dir.parent / "crystallized"

    def get_level0_index(self) -> str:
        """
        Level 0: Return compact progressive disclosure index of available strategies and active regimes
        with parsed YAML frontmatter descriptions.
        """
        from monika.application.skills.loader import parse_skill_frontmatter

        skills_summary: List[str] = []

        def _format_entry(file_path: Path, prefix: str) -> str:
            default_name = file_path.parent.name if file_path.name == "SKILL.md" else file_path.stem
            clean_name = default_name.replace("-", " ").replace("_", " ").title()
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    head = f.read(1024)
                meta, _ = parse_skill_frontmatter(head)
                name = meta.get("name") or clean_name
                desc = meta.get("description", "")
                if desc:
                    return f"- {prefix}: {name} — {desc.strip()[:50]}"
                return f"- {prefix}: {name}"
            except Exception:
                return f"- {prefix}: {clean_name}"

        # Scan trading playbooks
        if self.playbooks_dir.exists():
            for p in sorted(self.playbooks_dir.glob("*/SKILL.md")):
                skills_summary.append(_format_entry(p, "Playbook"))
            for p in sorted(self.playbooks_dir.glob("*.md")):
                if p.name != "SKILL.md":
                    skills_summary.append(_format_entry(p, "Playbook"))

        # Scan crystallized skills
        if self.crystallized_dir.exists():
            for c in sorted(self.crystallized_dir.glob("*/SKILL.md")):
                skills_summary.append(_format_entry(c, "Crystallized"))
            for c in sorted(self.crystallized_dir.glob("*.md")):
                if c.name != "SKILL.md":
                    skills_summary.append(_format_entry(c, "Crystallized"))

        if not skills_summary:
            return (
                "[AVAILABLE_PLAYBOOKS_INDEX (Level 0)]:\n"
                "<available_skills>\n"
                "- Playbook: Standard SMC/ICT and Macro Disciplinary Frameworks Active.\n"
                "</available_skills>"
            )

        selected: List[str] = []
        current_len = 75
        for item in skills_summary[:10]:
            if current_len + len(item) + 1 > 920:
                break
            selected.append(item)
            current_len += len(item) + 1
        entries = "\n".join(selected)
        return f"[AVAILABLE_PLAYBOOKS_INDEX (Level 0)]:\n<available_skills>\n{entries}\n</available_skills>"

    def get_level1_playbook(self, symbol: str) -> Optional[str]:
        """
        Level 1: Load symbol-specific or asset-class playbook.
        """
        clean_sym = symbol.strip().upper()
        sym_lower = clean_sym.lower()
        candidates = [
            self.playbooks_dir / sym_lower / "SKILL.md",
            self.playbooks_dir / f"{sym_lower}-playbook" / "SKILL.md",
            self.playbooks_dir / f"{sym_lower}_playbook" / "SKILL.md",
            self.playbooks_dir / f"{sym_lower}.md",
            self.playbooks_dir / f"{sym_lower}_playbook.md",
            self.crystallized_dir / sym_lower / "SKILL.md",
            self.crystallized_dir / f"{sym_lower}.md",
        ]
        for c in candidates:
            if c.exists():
                try:
                    with open(c, "r", encoding="utf-8") as f:
                        return f.read()
                except Exception as e:
                    logger.warning(f"Failed to read Level 1 playbook {c}: {e}")

        # Fallback to general SMC playbook if specific one does not exist
        for gen_smc in (
            self.base_dir / "smc-ict-playbook" / "SKILL.md",
            self.base_dir / "smc_ict_playbook" / "SKILL.md",
            self.base_dir / "smc_ict_playbook.md",
        ):
            if gen_smc.exists():
                try:
                    with open(gen_smc, "r", encoding="utf-8") as f:
                        return f.read()
                except Exception:
                    pass
        return None

    def get_level2_reference(self, topic: str) -> Optional[str]:
        """
        Level 2: Load granular tactical micro-reference on-demand.
        """
        clean_topic = topic.strip().lower().replace(" ", "_")
        refs_dir = self.base_dir / "references"
        if not refs_dir.exists():
            return None

        for ref_file in refs_dir.glob("*.md"):
            if clean_topic in ref_file.stem.lower():
                try:
                    with open(ref_file, "r", encoding="utf-8") as f:
                        return f.read()
                except Exception as e:
                    logger.warning(f"Failed to read Level 2 reference {ref_file}: {e}")
        return None


# Alias for backward compatibility
ProgressiveMemoryLoader = ProgressivePlaybookLoader

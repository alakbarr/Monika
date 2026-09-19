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

import os
import re
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger("TradingAgent.Memory.ProgressiveLoader")


class ProgressivePlaybookLoader:
    """Manages progressive 3-tier loading of trading playbooks."""

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            root = Path(__file__).resolve().parent.parent.parent
            self.base_dir = root / "skills" / "trading"

        self.playbooks_dir = self.base_dir / "playbooks"
        self.crystallized_dir = self.base_dir.parent / "crystallized"

    def get_level0_index(self) -> str:
        """
        Level 0: Return ultra-compact index of available strategies and active regimes.
        Consumes < 150 tokens.
        """
        skills_summary: List[str] = []

        # Scan trading playbooks
        if self.playbooks_dir.exists():
            for p in sorted(self.playbooks_dir.glob("*.md")):
                stem = p.stem.replace("_", " ").title()
                skills_summary.append(f"- Playbook: {stem}")

        # Scan crystallized skills
        if self.crystallized_dir.exists():
            for c in sorted(self.crystallized_dir.glob("*.md")):
                stem = c.stem.replace("_", " ").title()
                skills_summary.append(f"- Crystallized: {stem}")

        if not skills_summary:
            return "[AVAILABLE_PLAYBOOKS]: Standard SMC/ICT and Macro Disciplinary Frameworks Active."

        return "[AVAILABLE_PLAYBOOKS_INDEX (Level 0)]:\n" + "\n".join(skills_summary[:12])

    def get_level1_playbook(self, symbol: str) -> Optional[str]:
        """
        Level 1: Load symbol-specific or asset-class playbook.
        """
        clean_sym = symbol.strip().upper()
        candidates = [
            self.playbooks_dir / f"{clean_sym.lower()}.md",
            self.playbooks_dir / f"{clean_sym.lower()}_playbook.md",
            self.crystallized_dir / f"{clean_sym.lower()}.md",
        ]
        for c in candidates:
            if c.exists():
                try:
                    with open(c, "r", encoding="utf-8") as f:
                        return f.read()
                except Exception as e:
                    logger.warning(f"Failed to read Level 1 playbook {c}: {e}")

        # Fallback to general SMC playbook if specific one does not exist
        gen_smc = self.base_dir / "smc_ict_playbook.md"
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

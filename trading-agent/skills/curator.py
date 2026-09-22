"""
Skill lifecycle curator (Active -> Stale -> Archived).
Automates aging transitions and pruning of deprecated micro-playbooks without deleting historical data.
"""

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Union, FrozenSet

from skills.usage_tracker import SkillUsageTracker

logger = logging.getLogger("TradingAgent.Skills.Curator")


class SkillCurator:
    """Evaluates skill freshness and transitions stale or unused skills to archive."""

    STALE_AFTER_DAYS: int = 14
    ARCHIVE_AFTER_DAYS: int = 30

    PROTECTED_SKILLS: FrozenSet[str] = frozenset({
        "smc_ict_playbook",
        "macro_analysis_framework",
        "risk_management_principles",
        "session_timing_rules",
        "adjudication_framework",
        "central_banks_framework",
        "market_dynamics_framework",
        "caveman_mode",
    })

    def __init__(
        self,
        skills_dir: Optional[Union[str, Path]] = None,
        stale_days: Optional[int] = None,
        archive_days: Optional[int] = None,
    ):
        if skills_dir:
            self.skills_dir = Path(skills_dir).resolve()
        else:
            self.skills_dir = Path(__file__).resolve().parent

        self.stale_days = stale_days or self.STALE_AFTER_DAYS
        self.archive_days = archive_days or self.ARCHIVE_AFTER_DAYS
        self.archive_dir = self.skills_dir / ".archive"

    def apply_lifecycle_transitions(self, reference_time: Optional[datetime] = None) -> Dict[str, List[str]]:
        """
        Evaluates skills against age ladders:
        - Inactive >= stale_days -> Stale status
        - Inactive >= archive_days -> Moved to .archive/
        Protected core skills are completely immune.
        """
        now = reference_time or datetime.now(timezone.utc)
        results: Dict[str, List[str]] = {"active": [], "stale": [], "archived": []}

        if not self.skills_dir.exists():
            return results

        # Scan for markdown skill files (excluding .archive)
        for skill_file in self.skills_dir.glob("**/*.md"):
            # Skip files inside .archive
            if ".archive" in skill_file.parts:
                continue

            stem = skill_file.stem
            if stem in self.PROTECTED_SKILLS:
                results["active"].append(stem)
                continue

            telemetry = SkillUsageTracker.load(skill_file)
            last_activity_str = telemetry.get("last_used_at") or telemetry.get("created_at")

            days_idle = 0
            if last_activity_str:
                try:
                    dt = datetime.fromisoformat(last_activity_str.replace("Z", "+00:00"))
                    days_idle = max(0, (now - dt).days)
                except Exception:
                    days_idle = 0

            if days_idle >= self.archive_days:
                # Move to .archive directory
                rel_path = skill_file.relative_to(self.skills_dir)
                dest = self.archive_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.move(str(skill_file), str(dest))
                    # Also move .usage.json if present
                    usage_file = skill_file.parent / f"{skill_file.stem}.usage.json"
                    if usage_file.exists():
                        shutil.move(str(usage_file), str(dest.parent / usage_file.name))
                    results["archived"].append(stem)
                    logger.info(f"[SkillCurator] Archived idle skill '{stem}' ({days_idle} days idle).")
                except Exception as e:
                    logger.warning(f"[SkillCurator] Failed to archive skill '{stem}': {e}")
            elif days_idle >= self.stale_days:
                results["stale"].append(stem)
            else:
                results["active"].append(stem)

        return results

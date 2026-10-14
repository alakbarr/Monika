# ==============================================================================
# File: skills/continuous_learning.py
# ==============================================================================

"""
Continuous Self-Improvement & Experience Crystallization Engine.
Extracts procedural knowledge, user corrections, and failure post-mortems,
crystallizing them into persistent skills in 'skills/crystallized/' so Monika
never repeats previous errors and continuously expands domain capabilities.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel, Field

from monika.application.analysis.tools.unified_registry import unified_tool_registry

logger = logging.getLogger("TradingAgent.Skills.ContinuousLearning")

DEFAULT_CRYSTALLIZED_DIR = str(Path(__file__).resolve().parent / "crystallized")


class LearnSkillInput(BaseModel):
    """Schema for teaching Monika a new rule, procedure, or corrective guideline."""

    skill_name: str = Field(
        ...,
        description="Concise identifier for the learned skill (e.g. 'mt5_trailing_stop_rule', 'curl_proxy_workaround').",
    )
    description: str = Field(..., description="Brief summary of what this skill teaches or resolves (max 80 chars).")
    problem_or_mistake: str = Field(..., description="The error, constraint, or prior shortcoming encountered.")
    solution_procedure: str = Field(..., description="The step-by-step correct procedure to follow in the future.")
    category: Optional[str] = Field("crystallized", description="Target category folder (default 'crystallized').")


class ContinuousLearner:
    """
    Synthesizes learning experiences into standardized SKILL.md packages.
    """

    @classmethod
    def distill_and_crystallize(
        cls,
        skill_name: str,
        description: str,
        problem: str,
        solution: str,
        category: str = "crystallized",
        base_dir: Optional[Path | str] = None,
    ) -> Tuple[bool, str, str]:
        """
        Generates and saves a standardized SKILL.md file.
        Returns (success, message, file_path).
        """
        clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", skill_name.strip().lower())
        desc_clean = description.strip()[:80]

        parent_dir = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parent

        # Guard: Never allow overwriting core skills in trading or general
        for core_cat in ("trading", "general"):
            if (parent_dir / core_cat / clean_name).exists():
                return False, f"Cannot overwrite core system skill '{clean_name}' in category '{core_cat}'.", ""

        # Enforce category strictly to crystallized
        category = "crystallized"
        target_dir = parent_dir / category / clean_name
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / "SKILL.md"

        now_str = time.strftime("%Y-%m-%d %H:%M:%S")

        content = f"""---
name: {clean_name}
description: {desc_clean}
version: 1.0.0
category: {category.upper()}
learned_at: "{now_str}"
platforms:
  - windows
  - linux
  - macos
---

# Learned Skill: {clean_name}

## Problem & Context
{problem.strip()}

## Resolution & Standard Procedure
{solution.strip()}

## Verification Checklist
- [ ] Confirm context conditions match before applying.
- [ ] Execute exact validated steps above.
- [ ] Avoid repeating previously diagnosed pitfalls.
"""
        try:
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(content)

            # Security Audit via SkillsGuard
            from monika.application.skills.skills_guard import SkillsGuard

            report = SkillsGuard.audit_skill_directory(str(target_dir), skill_name=clean_name)
            if not report.is_safe:
                if target_file.exists():
                    target_file.unlink()
                reasons = [f.message for f in report.findings]
                return False, f"Skill '{clean_name}' failed security audit: {reasons}", ""

            # Invalidate skill loader cache so new skill is immediately recognized
            try:
                from monika.application.skills.loader import invalidate_cache

                invalidate_cache()
            except Exception:
                pass

            logger.info(f"[ContinuousLearner] Successfully crystallized skill '{clean_name}' at {target_file}")
            return True, f"Skill '{clean_name}' successfully crystallized into persistent memory.", str(target_file)
        except Exception as exc:
            return False, f"Failed writing skill file: {exc}", ""


@unified_tool_registry.register(
    name="learn_skill",
    category="CONTINUOUS_LEARNING",
    input_model=LearnSkillInput,
)
async def handle_learn_skill(
    params: LearnSkillInput,
    context: Optional[Any] = None,
) -> Dict[str, Any]:
    """Crystallizes a corrective procedure or new domain workflow into persistent skills."""
    ok, msg, path = ContinuousLearner.distill_and_crystallize(
        skill_name=params.skill_name,
        description=params.description,
        problem=params.problem_or_mistake,
        solution=params.solution_procedure,
        category=params.category or "crystallized",
    )
    return {
        "success": ok,
        "message": msg,
        "file_path": path,
    }

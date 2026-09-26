# ==============================================================================
# File: analysis/tools/domain/skill_tools.py
# ==============================================================================

"""
Universal Skills Domain Tools.
Two-tier progressive skill discovery, caching, deduplication, and execution.

Tools registered:
  - skills_list: Lists all available domain skills with high-level descriptions.
  - skill_view: Fetches full workflow instructions and linked resources on-demand.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from pydantic import BaseModel, Field

from analysis.tools.unified_registry import unified_tool_registry
from skills.skills_hub import SkillsHub

logger = logging.getLogger("TradingAgent.Tools.SkillTools")

# Global singleton SkillsHub instance
_SKILLS_HUB = SkillsHub()


def get_skills_hub() -> SkillsHub:
    """Return the global SkillsHub singleton."""
    return _SKILLS_HUB


class SkillsListInput(BaseModel):
    """Input parameters for listing available skills."""
    category: Optional[str] = Field(
        None,
        description="Filter skills by category (e.g. 'TRADING', 'GENERAL', 'CRYSTALLIZED'). Omit to list all."
    )


class SkillViewInput(BaseModel):
    """Input parameters for viewing specific skill instructions."""
    skill_name: str = Field(
        ...,
        description="Name of the skill to inspect."
    )
    file_path: Optional[str] = Field(
        None,
        description="Relative sub-path to a linked resource within the skill folder (e.g. 'references/rules.md')."
    )
    session_id: str = Field(
        "default",
        description="Active session ID for fingerprint caching and variable substitution."
    )


@unified_tool_registry.register(
    name="skills_list",
    category="KNOWLEDGE",
    input_model=SkillsListInput,
)
async def handle_skills_list(
    params: SkillsListInput,
    context: Optional[Any] = None,
) -> str:
    """List available skills with categories and concise descriptions."""
    skills = _SKILLS_HUB.list_skills(category=params.category)
    if not skills:
        return f"No skills found matching category: {params.category or 'ALL'}"
    return json.dumps(skills, indent=2)


@unified_tool_registry.register(
    name="skill_view",
    category="KNOWLEDGE",
    input_model=SkillViewInput,
)
async def handle_skill_view(
    params: SkillViewInput,
    context: Optional[Any] = None,
) -> str:
    """Fetch complete instructions and templates for a specific skill."""
    success, content = _SKILLS_HUB.view_skill(
        name=params.skill_name,
        file_path=params.file_path,
        session_id=params.session_id,
    )
    return content

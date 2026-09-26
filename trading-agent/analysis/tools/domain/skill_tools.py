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


class SkillManageInput(BaseModel):
    """Input parameters for managing skill definitions."""
    action: str = Field(
        ...,
        description="Action to perform: 'create', 'edit', 'delete', 'info', or 'hot_reload'."
    )
    name: Optional[str] = Field(
        None,
        description="Name of the skill to create, edit, delete, or inspect."
    )
    category: Optional[str] = Field(
        "general",
        description="Category for creation (e.g. 'general', 'trading', 'crystallized')."
    )
    description: Optional[str] = Field(
        None,
        description="Short description for new skill (< 80 chars)."
    )
    content: Optional[str] = Field(
        None,
        description="Full markdown content for creation or replacement edit."
    )
    old_text: Optional[str] = Field(
        None,
        description="Existing text block to replace during edit."
    )
    replacement_text: Optional[str] = Field(
        None,
        description="New text block to insert in place of old_text during edit."
    )
    fuzzy_match: bool = Field(
        True,
        description="Whether to use fuzzy matching for text block replacement if exact match fails."
    )
    force: bool = Field(
        False,
        description="Whether to force deletion of skills."
    )
    archive_instead: bool = Field(
        True,
        description="If true, move to archive instead of permanent deletion."
    )


@unified_tool_registry.register(
    name="skill_manage",
    category="KNOWLEDGE",
    input_model=SkillManageInput,
)
async def handle_skill_manage(
    params: SkillManageInput,
    context: Optional[Any] = None,
) -> str:
    """Manage domain skills lifecycle: create, edit, delete, inspect info, or hot-reload."""
    from skills.skill_manager import SkillManager
    manager = SkillManager(skills_hub=_SKILLS_HUB)

    action = params.action.strip().lower()

    if action == "hot_reload":
        res = manager.hot_reload()
        return json.dumps(res, indent=2)

    if action == "info":
        if not params.name:
            return "Error: 'name' is required for action 'info'."
        info = manager.get_skill_info(params.name)
        if not info:
            return f"Skill '{params.name}' not found."
        return json.dumps(info, indent=2)

    if action == "create":
        if not params.name or not params.content:
            return "Error: 'name' and 'content' are required for action 'create'."
        success, msg = manager.create_skill(
            name=params.name,
            content=params.content,
            category=params.category or "general",
            description=params.description,
            overwrite=params.force,
        )
        return msg

    if action == "edit":
        if not params.name:
            return "Error: 'name' is required for action 'edit'."
        success, msg = manager.edit_skill(
            name=params.name,
            new_content=params.content,
            old_text=params.old_text,
            replacement_text=params.replacement_text,
            fuzzy_match=params.fuzzy_match,
        )
        return msg

    if action == "delete":
        if not params.name:
            return "Error: 'name' is required for action 'delete'."
        success, msg = manager.delete_skill(
            name=params.name,
            force=params.force,
            archive_instead=params.archive_instead,
        )
        return msg

    return f"Unsupported action: '{params.action}'. Expected 'create', 'edit', 'delete', 'info', or 'hot_reload'."


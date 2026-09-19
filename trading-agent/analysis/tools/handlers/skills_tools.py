# ==============================================================================
# File: analysis/tools/handlers/skills_tools.py
# Description: Progressive disclosure tool handlers for trading skills & playbooks
# ==============================================================================

import logging
import re
from typing import Any, Dict, Optional, List
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import register_tool
from skills.loader import list_skills, load_skill, _SKILLS_DIR

logger = logging.getLogger("TradingAgent.Tools.Skills")


def _extract_summary(skill_name: str) -> str:
    """Extract a 1-sentence summary or title from the skill markdown file."""
    try:
        content = load_skill(skill_name)
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        for line in lines:
            if line.startswith("#"):
                clean = re.sub(r"^#+\s*", "", line).strip()
                return clean[:120]
            if not line.startswith("---") and not line.startswith("```") and len(line) > 10:
                return line[:120]
    except Exception:
        pass
    return f"Playbook for {skill_name.replace('_', ' ').title()}"


async def handle_skills_list(args: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
    """Return an index of all available institutional skills and playbooks."""
    all_names = list_skills()
    skills_meta: List[Dict[str, str]] = []

    for name in all_names:
        category = "tactical"
        if "framework" in name or "macro" in name or "banks" in name:
            category = "macro"
        elif "playbook" in name or "smc" in name:
            category = "technical"
        elif "principles" in name or "adjudication" in name or "soul" in name:
            category = "discipline"

        summary = _extract_summary(name)
        skills_meta.append({
            "name": name,
            "category": category,
            "summary": summary,
        })

    return {
        "status": "success",
        "total_skills": len(skills_meta),
        "skills": skills_meta,
    }


async def handle_skill_view(args: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """Retrieve the full content of a specific skill or playbook by name."""
    skill_name = args.get("skill_name", "").strip().removesuffix(".md")
    if not skill_name:
        return {
            "status": "error",
            "message": "Missing 'skill_name' parameter.",
            "available_skills": list_skills(),
        }

    try:
        content = load_skill(skill_name)
        return {
            "status": "success",
            "skill_name": skill_name,
            "length_chars": len(content),
            "content": content,
        }
    except FileNotFoundError:
        return {
            "status": "error",
            "message": f"Skill '{skill_name}' not found.",
            "available_skills": list_skills(),
        }
    except Exception as e:
        logger.warning(f"Failed to load skill '{skill_name}': {e}")
        return {
            "status": "error",
            "message": str(e),
        }


@register_tool("skills_list", aliases=["list_skills", "available_skills"], category="KNOWLEDGE", parallel_safe=True)
class SkillsListHandler(ToolHandler):
    name = "skills_list"
    category = "KNOWLEDGE"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_skills_list(args, session=session, executor=executor, **kwargs)


@register_tool("skill_view", aliases=["view_skill", "read_skill", "inspect_skill"], category="KNOWLEDGE", parallel_safe=True)
class SkillViewHandler(ToolHandler):
    name = "skill_view"
    category = "KNOWLEDGE"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_skill_view(args, session=session, executor=executor, **kwargs)

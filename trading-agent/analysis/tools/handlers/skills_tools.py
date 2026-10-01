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


from skills.usage_tracker import SkillUsageTracker
from skills.loader import get_skill_metadata


async def handle_skills_list(args: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
    """Return an index of all available institutional skills, versions, and usage statistics."""
    all_names = list_skills()
    skills_meta: List[Dict[str, Any]] = []

    for name in all_names:
        category = "tactical"
        if "framework" in name or "macro" in name or "banks" in name:
            category = "macro"
        elif "playbook" in name or "smc" in name:
            category = "technical"
        elif "principles" in name or "adjudication" in name or "soul" in name:
            category = "discipline"

        summary = _extract_summary(name)
        meta = get_skill_metadata(name) or {}
        version = meta.get("version", "1.0")
        
        # Load usage telemetry
        target_dir = _SKILLS_DIR / name
        usage = SkillUsageTracker.load(target_dir if target_dir.exists() else _SKILLS_DIR)
        
        skills_meta.append({
            "name": name,
            "category": category,
            "version": version,
            "summary": summary,
            "use_count": usage.get("use_count", 0),
            "view_count": usage.get("view_count", 0),
            "last_used_at": usage.get("last_used_at"),
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
        target_dir = _SKILLS_DIR / skill_name
        if target_dir.exists():
            SkillUsageTracker.record_view(target_dir)
        meta = get_skill_metadata(skill_name) or {}
        return {
            "status": "success",
            "skill_name": skill_name,
            "version": meta.get("version", "1.0"),
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


async def handle_create_skill(args: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """Create and persist a new skill markdown file using SkillManager."""
    skill_name = args.get("skill_name", "").strip().removesuffix(".md").replace(" ", "_").lower()
    content = args.get("content", "").strip()
    category = args.get("category", "trading").strip()
    description = args.get("description", "").strip()

    if not skill_name:
        return {"status": "error", "message": "Missing 'skill_name' parameter."}
    if not content:
        return {"status": "error", "message": "Missing 'content' parameter."}

    # Ensure valid frontmatter
    if not content.startswith("---"):
        frontmatter = f"---\nname: {skill_name}\ndescription: {description or skill_name}\ncategory: {category}\n---\n\n"
        content = frontmatter + content

    try:
        from skills.skill_manager import SkillManager
        manager = SkillManager()
        success, message, created_path = manager.create_skill(
            name=skill_name,
            content=content,
            category=category,
        )
        if success:
            return {
                "status": "success",
                "message": f"Successfully created skill '{skill_name}' at {created_path}",
                "skill_name": skill_name,
                "category": category,
            }
        else:
            return {
                "status": "error",
                "message": f"Failed to create skill '{skill_name}': {message}",
            }
    except Exception as e:
        logger.error(f"Error creating skill '{skill_name}': {e}")
        return {"status": "error", "message": str(e)}


@register_tool("create_skill", aliases=["learn_skill", "save_skill", "register_skill"], category="KNOWLEDGE", parallel_safe=False)
class CreateSkillHandler(ToolHandler):
    name = "create_skill"
    category = "KNOWLEDGE"
    parallel_safe = False

    async def execute(self, args: Dict[str, Any], session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_create_skill(args, session=session, executor=executor, **kwargs)


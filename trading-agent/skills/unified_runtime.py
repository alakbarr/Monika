# ==============================================================================
# File: skills/unified_runtime.py
# ==============================================================================

"""
Unified Skills Runtime with Two-Tier Progressive Disclosure.
Institutional-grade agent extensibility architecture.

Provides a unified facade combining lightweight prompt indexing (Tier 1)
and on-demand instruction disclosure with dynamic variable substitution (Tier 2).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from skills.skills_hub import SkillsHub, SkillMetadata

logger = logging.getLogger("TradingAgent.Skills.UnifiedRuntime")


class UnifiedSkillsRuntime:
    """
    Central runtime coordinator for discovering, indexing, matching,
    and dynamically loading modular skills with progressive disclosure.
    """

    def __init__(self, search_directories: Optional[List[str]] = None):
        self.hub = SkillsHub(search_directories=search_directories)

    def reload(self) -> int:
        return self.hub.discover_skills()

    def get_compact_prompt_index(self, max_skills: Optional[int] = None) -> str:
        """
        Tier 1 Progressive Disclosure:
        Generates a token-optimized markdown index summarizing available skills.
        Used at system prompt initialization with minimal token consumption.
        """
        all_skills = self.hub.list_skills()
        if max_skills is not None:
            all_skills = all_skills[:max_skills]

        lines = [
            "### Available Specialization Skills (Tier 1 Index):",
            "To activate a skill, request it by name or execute relevant domain tasks.",
        ]

        for s in all_skills:
            name = s.get("name") if isinstance(s, dict) else s.name
            cat = s.get("category") if isinstance(s, dict) else s.category
            desc = s.get("description") if isinstance(s, dict) else s.description
            tags = s.get("tags") if isinstance(s, dict) else getattr(s, "tags", [])
            tags_list = tags if isinstance(tags, list) else []
            tags_str = f" [tags: {', '.join(tags_list[:4])}]" if tags_list else ""
            lines.append(f"- **{name}** ({cat}): {desc}{tags_str}")

        return "\n".join(lines)

    def match_skills_for_prompt(self, prompt: str) -> List[str]:
        """
        Scans incoming prompt text for matches against skill names, categories, and tags.
        """
        if not prompt or not prompt.strip():
            return []

        lower_prompt = prompt.lower()
        matched: List[str] = []

        for s in self.hub.list_skills():
            name = s.get("name") if isinstance(s, dict) else s.name
            tags = s.get("tags") if isinstance(s, dict) else getattr(s, "tags", [])
            tags_list = tags if isinstance(tags, list) else []

            # Exact skill name match
            if name.lower() in lower_prompt:
                matched.append(name)
                continue

            # Tag matches
            for tag in tags_list:
                pattern = rf"\b{re.escape(str(tag).lower())}\b"
                if re.search(pattern, lower_prompt):
                    matched.append(name)
                    break

        return matched

    def load_skill_instructions(
        self,
        skill_name: str,
        context_vars: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Tier 2 Progressive Disclosure:
        Loads the complete, detailed instructions for a skill on-demand
        with variable substitution.
        """
        success, rendered = self.hub.view_skill(skill_name)
        if not success or not rendered:
            raise KeyError(f"Skill '{skill_name}' not found in registry: {rendered}")

        if context_vars:
            for k, v in context_vars.items():
                rendered = rendered.replace(f"${{{k}}}", str(v))
                rendered = rendered.replace(f"${k}", str(v))

        return rendered

    def list_skills(self) -> List[Dict[str, Any]]:
        return self.hub.list_skills()


_GLOBAL_SKILLS_RUNTIME: Optional[UnifiedSkillsRuntime] = None


def get_skills_runtime() -> UnifiedSkillsRuntime:
    global _GLOBAL_SKILLS_RUNTIME
    if _GLOBAL_SKILLS_RUNTIME is None:
        _GLOBAL_SKILLS_RUNTIME = UnifiedSkillsRuntime()
    return _GLOBAL_SKILLS_RUNTIME

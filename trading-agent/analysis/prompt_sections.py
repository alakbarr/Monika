# ==============================================================================
# File: analysis/prompt_sections.py
# ==============================================================================

"""
System Prompt Section Registry and Formatter for Monika LLM Prompts.
Allows plugins to register modular prompt blocks (context, instructions, guards)
without mutating core prompt files directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Union

logger = logging.getLogger("TradingAgent.PromptSections")

VALID_POSITIONS = {"before_instructions", "after_memory", "system_append"}
DEFAULT_MAX_CHARS = 2048


@dataclass
class PromptSection:
    id: str
    content: Union[str, Callable[[Mapping[str, Any]], str]]
    position: str = "after_memory"
    max_chars: int = DEFAULT_MAX_CHARS
    plugin_id: str = ""


class PromptSectionRegistry:
    """Registry managing dynamically registered system prompt sections."""

    _instance: Optional["PromptSectionRegistry"] = None

    def __init__(self):
        self._sections: Dict[str, PromptSection] = {}

    @classmethod
    def get_instance(cls) -> "PromptSectionRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(
        self,
        section_id: str,
        content: Union[str, Callable[[Mapping[str, Any]], str]],
        position: str = "after_memory",
        max_chars: int = DEFAULT_MAX_CHARS,
        plugin_id: str = "",
    ) -> bool:
        clean_id = section_id.strip().lower()
        if not clean_id:
            logger.warning("Rejected prompt section with empty ID.")
            return False

        if position not in VALID_POSITIONS:
            logger.warning(f"Invalid position '{position}' for section '{clean_id}'. Defaulting to 'after_memory'.")
            position = "after_memory"

        self._sections[clean_id] = PromptSection(
            id=clean_id,
            content=content,
            position=position,
            max_chars=max_chars,
            plugin_id=plugin_id,
        )
        logger.debug(f"[PromptSections] Registered section '{clean_id}' at position '{position}' by '{plugin_id}'")
        return True

    def unregister(self, section_id: str) -> bool:
        clean_id = section_id.strip().lower()
        if clean_id in self._sections:
            del self._sections[clean_id]
            logger.debug(f"[PromptSections] Unregistered section '{clean_id}'")
            return True
        return False

    def get_rendered_sections(
        self,
        position: Optional[str] = None,
        context: Optional[Mapping[str, Any]] = None,
    ) -> List[str]:
        """Render all active sections matching position, clamped to max_chars."""
        ctx = context or {}
        rendered = []
        for s in self._sections.values():
            if position and s.position != position:
                continue
            try:
                if callable(s.content):
                    import inspect
                    sig = inspect.signature(s.content)
                    if len(sig.parameters) == 0:
                        text = str(s.content())
                    else:
                        text = str(s.content(ctx))
                else:
                    text = str(s.content)

                if len(text) > s.max_chars:
                    text = text[: s.max_chars] + "… [section truncated]"
                rendered.append(text.strip())
            except Exception as e:
                logger.error(f"[PromptSections] Failed rendering section '{s.id}': {e}")
        return rendered

    def get_sections(self, position: Optional[str] = None) -> List[str]:
        """Convenience alias for get_rendered_sections."""
        return self.get_rendered_sections(position=position)

    def render_prefix(self, context: Optional[Mapping[str, Any]] = None) -> str:
        """Render all sections registered for 'before_instructions'."""
        before = self.get_rendered_sections("before_instructions", context)
        return "\n\n".join(before)

    def format_full_prompt(
        self,
        base_prompt: str,
        context: Optional[Mapping[str, Any]] = None,
    ) -> str:
        """Compose base prompt with all registered sections at appropriate positions."""
        before = self.get_rendered_sections("before_instructions", context)
        after_mem = self.get_rendered_sections("after_memory", context)
        append = self.get_rendered_sections("system_append", context)

        parts = []
        if before:
            parts.append("\n\n".join(before))
        if base_prompt:
            parts.append(base_prompt)
        if after_mem:
            parts.append("\n\n".join(after_mem))
        if append:
            parts.append("\n\n".join(append))

        return "\n\n".join(parts)


def get_prompt_section_registry() -> PromptSectionRegistry:
    return PromptSectionRegistry.get_instance()


# Default singleton instance exported for convenience
prompt_section_registry: PromptSectionRegistry = PromptSectionRegistry.get_instance()


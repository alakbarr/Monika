"""Prompt Assembly and Engineering Engine."""

from .prompt_assembler import (
    MANDATORY_RULES,
    STAGE1_TIER1,
    STAGE2_TIER1,
    STAGE2_TIER1_TEMPLATE,
    TIER2_TOOL_STUBS,
    PromptAssembler,
    _flatten_system_prompt,
    _split_memory,
)

__all__ = [
    "PromptAssembler",
    "STAGE1_TIER1",
    "STAGE2_TIER1",
    "STAGE2_TIER1_TEMPLATE",
    "MANDATORY_RULES",
    "TIER2_TOOL_STUBS",
    "_flatten_system_prompt",
    "_split_memory",
]

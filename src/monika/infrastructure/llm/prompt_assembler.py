"""
File: monika.infrastructure.llm.prompt_assembler
Backward-compatible proxy facade.
Canonical implementation has moved to `monika.application.analysis.prompt.prompt_assembler`.
"""

from monika.application.analysis.prompt.prompt_assembler import (
    MANDATORY_RULES,
    SECTION_ORDERS,
    STAGE1_TIER1,
    STAGE2_TIER1,
    STAGE2_TIER1_TEMPLATE,
    TIER2_TOOL_STUBS,
    PromptAssembler,
    PromptSection,
    _flatten_system_prompt,
    _split_memory,
    compare_sections,
    compose_ordered_prompt,
)

__all__ = [
    "PromptAssembler",
    "PromptSection",
    "SECTION_ORDERS",
    "STAGE1_TIER1",
    "STAGE2_TIER1",
    "STAGE2_TIER1_TEMPLATE",
    "MANDATORY_RULES",
    "TIER2_TOOL_STUBS",
    "_flatten_system_prompt",
    "_split_memory",
    "compare_sections",
    "compose_ordered_prompt",
]

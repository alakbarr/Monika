"""
Compatibility facade shim for legacy prompt_assembler.py.
Re-exports from canonical monika.infrastructure.llm.prompt_assembler.
"""

from __future__ import annotations

import monika.infrastructure.llm.prompt_assembler as _canonical

from monika.infrastructure.llm.prompt_assembler import (
    MANDATORY_RULES,
    PromptAssembler,
    PromptSection,
    STAGE1_TIER1,
    STAGE2_TIER1,
    STAGE2_TIER1_TEMPLATE,
    TIER2_TOOL_STUBS,
    compare_sections,
    compose_ordered_prompt,
)

__all__ = ['MANDATORY_RULES', 'PromptAssembler', 'PromptSection', 'STAGE1_TIER1', 'STAGE2_TIER1', 'STAGE2_TIER1_TEMPLATE', 'TIER2_TOOL_STUBS', 'compare_sections', 'compose_ordered_prompt']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical

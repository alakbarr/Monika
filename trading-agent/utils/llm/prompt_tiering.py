"""
Compatibility facade shim for legacy prompt_tiering.py.
Re-exports from canonical monika.infrastructure.llm.prompt_tiering.
"""

from __future__ import annotations

import monika.infrastructure.llm.prompt_tiering as _canonical

from monika.infrastructure.llm.prompt_tiering import (
    PromptTier,
    TieredPrompt,
    TieredSystemPrompt,
    build_tiered_prompt,
)

__all__ = ['PromptTier', 'TieredPrompt', 'TieredSystemPrompt', 'build_tiered_prompt']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical

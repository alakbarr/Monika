"""
Compatibility facade shim for legacy prompt_compressor.py.
Re-exports from canonical monika.infrastructure.llm.prompt_compressor.
"""

from __future__ import annotations

import monika.infrastructure.llm.prompt_compressor as _canonical

from monika.infrastructure.llm.prompt_compressor import (
    PromptBundleCompressor,
    estimate_tokens,
    truncate_to_budget,
)

__all__ = ['PromptBundleCompressor', 'estimate_tokens', 'truncate_to_budget']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical

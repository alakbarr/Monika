"""
Compatibility facade shim for legacy prompt_ab_test.py.
Re-exports from canonical monika.infrastructure.llm.prompt_ab_test.
"""

from __future__ import annotations

import monika.infrastructure.llm.prompt_ab_test as _canonical

from monika.infrastructure.llm.prompt_ab_test import (
    OfflinePromptOptimizer,
    PromptABTest,
)

__all__ = ['OfflinePromptOptimizer', 'PromptABTest']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical

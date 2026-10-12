"""
Compatibility facade shim for legacy constrained_sampling.py.
Re-exports from canonical monika.infrastructure.llm.constrained_sampling.
"""

from __future__ import annotations

import monika.infrastructure.llm.constrained_sampling as _canonical

from monika.infrastructure.llm.constrained_sampling import (
    ConstrainedSamplingConfig,
    make_strict_json_schema,
    resolve_grammar_for_provider,
)

__all__ = ['ConstrainedSamplingConfig', 'make_strict_json_schema', 'resolve_grammar_for_provider']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical

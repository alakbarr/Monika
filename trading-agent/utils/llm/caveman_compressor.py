"""
Compatibility facade shim for legacy caveman_compressor.py.
Re-exports from canonical monika.infrastructure.llm.caveman_compressor.
"""

from __future__ import annotations

import monika.infrastructure.llm.caveman_compressor as _canonical

from monika.infrastructure.llm.caveman_compressor import (
    compress_tool_payload,
)

__all__ = ['compress_tool_payload']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical

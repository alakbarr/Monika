"""
Compatibility facade shim for legacy tool_response_validator.py.
Re-exports from canonical monika.core.validation.tool_response_validator.
"""

from __future__ import annotations

import monika.core.validation.tool_response_validator as _canonical

from monika.core.validation.tool_response_validator import (
    ToolResponseValidator,
)

__all__ = ['ToolResponseValidator']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical

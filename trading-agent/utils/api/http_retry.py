"""
Compatibility facade shim for legacy http_retry.py.
Re-exports from canonical monika.infrastructure.api.http_retry.
"""

from __future__ import annotations

import monika.infrastructure.api.http_retry as _canonical

from monika.infrastructure.api.http_retry import (
    APIStatusError,
    RateLimitError,
    fetch_with_retry,
    format_api_error_summary,
    _CIRCUIT_BREAKER,
)

__all__ = ['APIStatusError', 'RateLimitError', 'fetch_with_retry', 'format_api_error_summary', '_CIRCUIT_BREAKER']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical

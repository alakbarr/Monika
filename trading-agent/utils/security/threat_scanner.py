"""
Compatibility facade shim for legacy threat_scanner.py.
Re-exports from canonical monika.core.security.threat_scanner.
"""

from __future__ import annotations

import monika.core.security.threat_scanner as _canonical

from monika.core.security.threat_scanner import (
    sanitize_or_block,
    scan_content,
)

__all__ = ['sanitize_or_block', 'scan_content']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical

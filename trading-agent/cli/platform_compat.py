"""
Compatibility facade shim for legacy platform_compat.py.
Re-exports from canonical monika.interfaces.cli.platform_compat.
"""

from __future__ import annotations

import monika.interfaces.cli.platform_compat as _canonical

from monika.interfaces.cli.platform_compat import (
    ColorDepth,
    apply_platform_fixes,
    detect_color_depth,
    detect_unicode_support,
    enable_windows_vt_mode,
    ensure_utf8_streams,
)

__all__ = ['ColorDepth', 'apply_platform_fixes', 'detect_color_depth', 'detect_unicode_support', 'enable_windows_vt_mode', 'ensure_utf8_streams']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical

"""
Compatibility facade shim for legacy threat_detector.py.
Re-exports from canonical monika.core.security.threat_detector.
"""

from __future__ import annotations

import monika.core.security.threat_detector as _canonical

from monika.core.security.threat_detector import (
    EXFILTRATION_PATTERNS,
    INJECTION_PATTERNS,
    ThreatDetector,
)

__all__ = ['EXFILTRATION_PATTERNS', 'INJECTION_PATTERNS', 'ThreatDetector']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical

"""
Compatibility facade shim for legacy prompt_injection_scanner.py.
Re-exports from canonical monika.core.security.prompt_injection_scanner.
"""

from __future__ import annotations

import monika.core.security.prompt_injection_scanner as _canonical

from monika.core.security.prompt_injection_scanner import (
    InjectionScanResult,
    PromptInjectionScanner,
    PromptInjectionThreatDetected,
    logger,
)

__all__ = ['InjectionScanResult', 'PromptInjectionScanner', 'PromptInjectionThreatDetected', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical

"""
Compatibility facade shim for legacy voice_safety_gate.py.
Re-exports from canonical monika.interfaces.telegram.voice_safety_gate.
"""

from __future__ import annotations

import monika.interfaces.telegram.voice_safety_gate as _canonical

from monika.interfaces.telegram.voice_safety_gate import (
    VoiceSafetyGate,
    VoiceTradeProposal,
    logger,
)

__all__ = ['VoiceSafetyGate', 'VoiceTradeProposal', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical

"""
Compatibility facade shim for legacy run_card.py.
Re-exports from canonical monika.core.telemetry.run_card.
"""

from __future__ import annotations

import monika.core.telemetry.run_card as _canonical

from monika.core.telemetry.run_card import (
    RunCardGenerator,
    generate_run_card,
    logger,
    verify_run_card,
)

__all__ = ['RunCardGenerator', 'generate_run_card', 'logger', 'verify_run_card']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical

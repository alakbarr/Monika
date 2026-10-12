"""
Compatibility facade shim for legacy onboarding_trader.py.
Re-exports from canonical monika.interfaces.cli.onboarding_trader.
"""

from __future__ import annotations

import monika.interfaces.cli.onboarding_trader as _canonical

from monika.interfaces.cli.onboarding_trader import (
    TraderOnboarding,
    TraderProfile,
    logger,
)

__all__ = ['TraderOnboarding', 'TraderProfile', 'logger']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical

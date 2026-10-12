"""
Compatibility facade shim for legacy adversarial_outcome_tracker.py.
Re-exports from canonical monika.core.analytics.adversarial_outcome_tracker.
"""

from __future__ import annotations

import monika.core.analytics.adversarial_outcome_tracker as _canonical

from monika.core.analytics.adversarial_outcome_tracker import (
    compute_adversarial_check_correlation,
)

__all__ = ['compute_adversarial_check_correlation']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical

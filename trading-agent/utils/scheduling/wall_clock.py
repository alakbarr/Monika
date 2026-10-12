"""
Compatibility facade shim for legacy wall_clock.py.
Re-exports from canonical monika.application.scheduler.wall_clock.
"""

from __future__ import annotations

import monika.application.scheduler.wall_clock as _canonical

from monika.application.scheduler.wall_clock import (
    get_tzinfo,
    next_occurrence,
    parse_time_list,
    previous_occurrence,
    sleep_until_next,
)

__all__ = ['get_tzinfo', 'next_occurrence', 'parse_time_list', 'previous_occurrence', 'sleep_until_next']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical

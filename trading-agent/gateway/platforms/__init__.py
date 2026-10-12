"""Compatibility facade shim for legacy platforms package."""
from __future__ import annotations
import monika.interfaces.gateway.platforms as _canonical
from monika.interfaces.gateway.platforms import *  # noqa: F401, F403
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

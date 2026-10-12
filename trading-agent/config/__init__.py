"""Compatibility facade shim for legacy config package."""
from __future__ import annotations
import monika.core.config as _canonical
from monika.core.config import *  # noqa: F401, F403
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

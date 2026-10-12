"""Compatibility facade shim for legacy overlays package."""
from __future__ import annotations
import monika.interfaces.cli.overlays as _canonical
from monika.interfaces.cli.overlays import *  # noqa: F401, F403
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

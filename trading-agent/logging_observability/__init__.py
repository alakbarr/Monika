"""Compatibility facade shim for legacy logging_observability package."""
from __future__ import annotations
import monika.core.telemetry as _canonical
from monika.core.telemetry import *  # noqa: F401, F403
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

"""Compatibility facade shim for legacy tracing subpackage."""
from __future__ import annotations
import monika.core.telemetry.tracing as _canonical
from monika.core.telemetry.tracing import *  # noqa: F401, F403
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

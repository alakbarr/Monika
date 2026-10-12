"""Compatibility facade shim for legacy reporting subpackage."""
from __future__ import annotations
import monika.core.telemetry.reporting as _canonical
from monika.core.telemetry.reporting import *  # noqa: F401, F403
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

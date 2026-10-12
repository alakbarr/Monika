"""Shim package: monika.application.protocol."""

import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.protocol")

for _attr in dir(_canonical):
    if not _attr.startswith("_"):
        globals()[_attr] = getattr(_canonical, _attr)

if hasattr(_canonical, "__all__"):
    __all__ = _canonical.__all__

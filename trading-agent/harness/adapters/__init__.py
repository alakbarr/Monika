"""Shim package: monika.application.harness.adapters."""

import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.harness.adapters")

for _attr in dir(_canonical):
    if not _attr.startswith("_"):
        globals()[_attr] = getattr(_canonical, _attr)

if hasattr(_canonical, "__all__"):
    __all__ = _canonical.__all__

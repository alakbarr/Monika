"""Shim module: monika.application.agent.error_classifier."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.agent.error_classifier")
_sys.modules[__name__] = _canonical

"""Shim module: monika.application.agent.state_rewind."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.agent.state_rewind")
_sys.modules[__name__] = _canonical

"""Shim module: monika.application.agent.trajectory_compressor."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.agent.trajectory_compressor")
_sys.modules[__name__] = _canonical

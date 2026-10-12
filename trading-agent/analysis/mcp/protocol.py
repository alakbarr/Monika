"""Shim module: monika.application.analysis.mcp.protocol."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.mcp.protocol import *

_canonical = _importlib.import_module("monika.application.analysis.mcp.protocol")
_sys.modules[__name__] = _canonical

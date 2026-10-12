"""Shim module: monika.application.analysis.mcp.server."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.mcp.server import *

_canonical = _importlib.import_module("monika.application.analysis.mcp.server")
_sys.modules[__name__] = _canonical

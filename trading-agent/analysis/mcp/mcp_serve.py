"""Shim module: monika.application.analysis.mcp.mcp_serve."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.mcp.mcp_serve import *

_canonical = _importlib.import_module("monika.application.analysis.mcp.mcp_serve")
_sys.modules[__name__] = _canonical

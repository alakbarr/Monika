"""Shim module: monika.application.analysis.mcp.dispatcher."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.mcp.dispatcher import *

_canonical = _importlib.import_module("monika.application.analysis.mcp.dispatcher")
_sys.modules[__name__] = _canonical

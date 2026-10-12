"""Shim module: monika.application.analysis.mcp.client."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.mcp.client import *

_canonical = _importlib.import_module("monika.application.analysis.mcp.client")
_sys.modules[__name__] = _canonical

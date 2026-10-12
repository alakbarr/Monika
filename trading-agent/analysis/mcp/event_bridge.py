"""Shim module: monika.application.analysis.mcp.event_bridge."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.mcp.event_bridge import *

_canonical = _importlib.import_module("monika.application.analysis.mcp.event_bridge")
_sys.modules[__name__] = _canonical

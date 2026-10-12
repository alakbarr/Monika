"""Shim module: monika.application.analysis.mcp.oauth_handler."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.mcp.oauth_handler import *

_canonical = _importlib.import_module("monika.application.analysis.mcp.oauth_handler")
_sys.modules[__name__] = _canonical

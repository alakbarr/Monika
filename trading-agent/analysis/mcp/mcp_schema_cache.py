"""Shim module: monika.application.analysis.mcp.mcp_schema_cache."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.mcp.mcp_schema_cache import *

_canonical = _importlib.import_module("monika.application.analysis.mcp.mcp_schema_cache")
_sys.modules[__name__] = _canonical

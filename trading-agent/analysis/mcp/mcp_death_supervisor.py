"""Shim module: monika.application.analysis.mcp.mcp_death_supervisor."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.mcp.mcp_death_supervisor import *

_canonical = _importlib.import_module("monika.application.analysis.mcp.mcp_death_supervisor")
_sys.modules[__name__] = _canonical

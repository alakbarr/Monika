"""Shim module: monika.application.analysis.mcp.servers.excel_server."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.mcp.servers.excel_server import *

_canonical = _importlib.import_module("monika.application.analysis.mcp.servers.excel_server")
_sys.modules[__name__] = _canonical

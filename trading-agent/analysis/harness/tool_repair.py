"""Shim module: monika.application.analysis.harness.tool_repair."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.harness.tool_repair import *

_canonical = _importlib.import_module("monika.application.analysis.harness.tool_repair")
_sys.modules[__name__] = _canonical

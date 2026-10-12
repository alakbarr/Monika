"""Shim module: monika.application.analysis.tools.tool_search_engine."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.tool_search_engine import *

_canonical = _importlib.import_module("monika.application.analysis.tools.tool_search_engine")
_sys.modules[__name__] = _canonical

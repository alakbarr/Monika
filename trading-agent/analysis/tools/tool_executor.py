"""Shim module: monika.application.analysis.tools.tool_executor."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.tool_executor import *

_canonical = _importlib.import_module("monika.application.analysis.tools.tool_executor")
_sys.modules[__name__] = _canonical

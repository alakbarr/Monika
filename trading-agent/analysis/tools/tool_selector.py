"""Shim module: monika.application.analysis.tools.tool_selector."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.tool_selector import *

_canonical = _importlib.import_module("monika.application.analysis.tools.tool_selector")
_sys.modules[__name__] = _canonical

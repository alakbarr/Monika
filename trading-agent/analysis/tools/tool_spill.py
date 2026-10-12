"""Shim module: monika.application.analysis.tools.tool_spill."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.tool_spill import *

_canonical = _importlib.import_module("monika.application.analysis.tools.tool_spill")
_sys.modules[__name__] = _canonical

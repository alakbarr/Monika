"""Shim module: monika.application.analysis.tools.handlers.advanced_quant_tools."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.handlers.advanced_quant_tools import *

_canonical = _importlib.import_module("monika.application.analysis.tools.handlers.advanced_quant_tools")
_sys.modules[__name__] = _canonical

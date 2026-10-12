"""Shim module: monika.application.analysis.tools.composite_tools."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.composite_tools import *

_canonical = _importlib.import_module("monika.application.analysis.tools.composite_tools")
_sys.modules[__name__] = _canonical

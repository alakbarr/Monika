"""Shim module: monika.application.analysis.tools.handlers.macro_data."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.handlers.macro_data import *

_canonical = _importlib.import_module("monika.application.analysis.tools.handlers.macro_data")
_sys.modules[__name__] = _canonical

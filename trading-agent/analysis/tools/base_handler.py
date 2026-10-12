"""Shim module: monika.application.analysis.tools.base_handler."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.base_handler import *

_canonical = _importlib.import_module("monika.application.analysis.tools.base_handler")
_sys.modules[__name__] = _canonical

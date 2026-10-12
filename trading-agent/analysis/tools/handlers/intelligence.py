"""Shim module: monika.application.analysis.tools.handlers.intelligence."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.handlers.intelligence import *

_canonical = _importlib.import_module("monika.application.analysis.tools.handlers.intelligence")
_sys.modules[__name__] = _canonical

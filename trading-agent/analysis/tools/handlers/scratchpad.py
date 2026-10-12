"""Shim module: monika.application.analysis.tools.handlers.scratchpad."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.handlers.scratchpad import *

_canonical = _importlib.import_module("monika.application.analysis.tools.handlers.scratchpad")
_sys.modules[__name__] = _canonical

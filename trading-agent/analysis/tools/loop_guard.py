"""Shim module: monika.application.analysis.tools.loop_guard."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.loop_guard import *

_canonical = _importlib.import_module("monika.application.analysis.tools.loop_guard")
_sys.modules[__name__] = _canonical

"""Shim module: monika.application.analysis.tools.tools_definitions."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.tools_definitions import *

_canonical = _importlib.import_module("monika.application.analysis.tools.tools_definitions")
_sys.modules[__name__] = _canonical

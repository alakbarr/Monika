"""Shim module: monika.application.analysis.tools.handlers.system_info."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.handlers.system_info import *

_canonical = _importlib.import_module("monika.application.analysis.tools.handlers.system_info")
_sys.modules[__name__] = _canonical

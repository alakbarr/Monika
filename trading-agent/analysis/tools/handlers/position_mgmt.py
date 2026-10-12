"""Shim module: monika.application.analysis.tools.handlers.position_mgmt."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.handlers.position_mgmt import *

_canonical = _importlib.import_module("monika.application.analysis.tools.handlers.position_mgmt")
_sys.modules[__name__] = _canonical

"""Shim module: monika.application.execution.service.emergency_manager."""

import sys as _sys
import importlib as _importlib

from monika.application.execution.service.emergency_manager import *

_canonical = _importlib.import_module("monika.application.execution.service.emergency_manager")
_sys.modules[__name__] = _canonical

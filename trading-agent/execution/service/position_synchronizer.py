"""Shim module: monika.application.execution.service.position_synchronizer."""

import sys as _sys
import importlib as _importlib

from monika.application.execution.service.position_synchronizer import *

_canonical = _importlib.import_module("monika.application.execution.service.position_synchronizer")
_sys.modules[__name__] = _canonical

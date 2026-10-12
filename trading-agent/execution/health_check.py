"""Shim module: monika.application.execution.health_check."""

import sys as _sys
import importlib as _importlib

from monika.application.execution.health_check import *

_canonical = _importlib.import_module("monika.application.execution.health_check")
_sys.modules[__name__] = _canonical

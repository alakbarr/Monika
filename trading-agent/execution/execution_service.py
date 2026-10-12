"""Shim module: monika.application.execution.execution_service."""

import sys as _sys
import importlib as _importlib

from monika.application.execution.execution_service import *

_canonical = _importlib.import_module("monika.application.execution.execution_service")
_sys.modules[__name__] = _canonical

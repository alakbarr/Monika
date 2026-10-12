"""Shim module: monika.application.execution.service.self_healing_executor."""

import sys as _sys
import importlib as _importlib

from monika.application.execution.service.self_healing_executor import *

_canonical = _importlib.import_module("monika.application.execution.service.self_healing_executor")
_sys.modules[__name__] = _canonical

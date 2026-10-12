"""Shim module: monika.application.execution.service.risk_evaluator."""

import sys as _sys
import importlib as _importlib

from monika.application.execution.service.risk_evaluator import *

_canonical = _importlib.import_module("monika.application.execution.service.risk_evaluator")
_sys.modules[__name__] = _canonical

"""Shim module: monika.application.execution.effect_gate."""

import sys as _sys
import importlib as _importlib

from monika.application.execution.effect_gate import *

_canonical = _importlib.import_module("monika.application.execution.effect_gate")
_sys.modules[__name__] = _canonical

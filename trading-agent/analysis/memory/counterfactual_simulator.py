"""Shim module: monika.application.analysis.memory.counterfactual_simulator."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.counterfactual_simulator import *

_canonical = _importlib.import_module("monika.application.analysis.memory.counterfactual_simulator")
_sys.modules[__name__] = _canonical

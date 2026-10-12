"""Shim module: monika.application.evals.simulation_clock."""

import sys as _sys
import importlib as _importlib

from monika.application.evals.simulation_clock import *

_canonical = _importlib.import_module("monika.application.evals.simulation_clock")
_sys.modules[__name__] = _canonical

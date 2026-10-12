"""Shim module: monika.application.analysis.harness.harness_state."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.harness.harness_state import *

_canonical = _importlib.import_module("monika.application.analysis.harness.harness_state")
_sys.modules[__name__] = _canonical

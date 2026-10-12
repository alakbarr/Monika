"""Shim module: monika.application.analysis.harness.repetition_guard."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.harness.repetition_guard import *

_canonical = _importlib.import_module("monika.application.analysis.harness.repetition_guard")
_sys.modules[__name__] = _canonical

"""Shim module: monika.application.analysis.validators.in_harness_grounding."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.validators.in_harness_grounding import *

_canonical = _importlib.import_module("monika.application.analysis.validators.in_harness_grounding")
_sys.modules[__name__] = _canonical

"""Shim module: monika.application.analysis.harness.structured_output."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.harness.structured_output import *

_canonical = _importlib.import_module("monika.application.analysis.harness.structured_output")
_sys.modules[__name__] = _canonical

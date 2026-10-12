"""Shim module: monika.application.analysis.harness.error_classifier."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.harness.error_classifier import *

_canonical = _importlib.import_module("monika.application.analysis.harness.error_classifier")
_sys.modules[__name__] = _canonical

"""Shim module: monika.application.analysis.validators.adversarial_check."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.validators.adversarial_check import *

_canonical = _importlib.import_module("monika.application.analysis.validators.adversarial_check")
_sys.modules[__name__] = _canonical

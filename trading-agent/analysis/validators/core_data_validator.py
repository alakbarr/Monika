"""Shim module: monika.application.analysis.validators.core_data_validator."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.validators.core_data_validator import *

_canonical = _importlib.import_module("monika.application.analysis.validators.core_data_validator")
_sys.modules[__name__] = _canonical

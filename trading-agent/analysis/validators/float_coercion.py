"""Shim module: monika.application.analysis.validators.float_coercion."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.validators.float_coercion import *

_canonical = _importlib.import_module("monika.application.analysis.validators.float_coercion")
_sys.modules[__name__] = _canonical

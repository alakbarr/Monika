"""Shim module: monika.application.analysis.debate.exact_decimal_math."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.debate.exact_decimal_math import *

_canonical = _importlib.import_module("monika.application.analysis.debate.exact_decimal_math")
_sys.modules[__name__] = _canonical

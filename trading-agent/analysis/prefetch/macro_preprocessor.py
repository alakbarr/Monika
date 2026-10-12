"""Shim module: monika.application.analysis.prefetch.macro_preprocessor."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.prefetch.macro_preprocessor import *

_canonical = _importlib.import_module("monika.application.analysis.prefetch.macro_preprocessor")
_sys.modules[__name__] = _canonical

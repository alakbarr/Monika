"""Shim module: monika.application.analysis.validators.fundamental_verifier."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.validators.fundamental_verifier import *

_canonical = _importlib.import_module("monika.application.analysis.validators.fundamental_verifier")
_sys.modules[__name__] = _canonical

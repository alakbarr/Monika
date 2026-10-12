"""Shim module: monika.application.analysis.validators.output_verifier."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.validators.output_verifier import *

_canonical = _importlib.import_module("monika.application.analysis.validators.output_verifier")
_sys.modules[__name__] = _canonical

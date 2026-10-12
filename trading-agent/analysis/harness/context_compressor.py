"""Shim module: monika.application.analysis.harness.context_compressor."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.harness.context_compressor import *

_canonical = _importlib.import_module("monika.application.analysis.harness.context_compressor")
_sys.modules[__name__] = _canonical

"""Shim module: monika.application.analysis.prefetch.digest_slice_generator."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.prefetch.digest_slice_generator import *

_canonical = _importlib.import_module("monika.application.analysis.prefetch.digest_slice_generator")
_sys.modules[__name__] = _canonical

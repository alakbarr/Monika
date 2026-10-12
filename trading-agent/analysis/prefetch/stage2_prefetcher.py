"""Shim module: monika.application.analysis.prefetch.stage2_prefetcher."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.prefetch.stage2_prefetcher import *

_canonical = _importlib.import_module("monika.application.analysis.prefetch.stage2_prefetcher")
_sys.modules[__name__] = _canonical

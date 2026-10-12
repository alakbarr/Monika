"""Shim module: monika.application.analysis.prefetch.stage1_prefetcher."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.prefetch.stage1_prefetcher import *

_canonical = _importlib.import_module("monika.application.analysis.prefetch.stage1_prefetcher")
_sys.modules[__name__] = _canonical

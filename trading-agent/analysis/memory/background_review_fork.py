"""Shim module: monika.application.analysis.memory.background_review_fork."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.background_review_fork import *

_canonical = _importlib.import_module("monika.application.analysis.memory.background_review_fork")
_sys.modules[__name__] = _canonical

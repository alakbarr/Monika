"""Shim module: monika.application.analysis.journal.attribution_engine."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.journal.attribution_engine import *

_canonical = _importlib.import_module("monika.application.analysis.journal.attribution_engine")
_sys.modules[__name__] = _canonical

"""Shim module: monika.application.analysis.journal.behavioral_diagnostics."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.journal.behavioral_diagnostics import *

_canonical = _importlib.import_module("monika.application.analysis.journal.behavioral_diagnostics")
_sys.modules[__name__] = _canonical

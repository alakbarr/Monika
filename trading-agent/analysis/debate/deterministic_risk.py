"""Shim module: monika.application.analysis.debate.deterministic_risk."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.debate.deterministic_risk import *

_canonical = _importlib.import_module("monika.application.analysis.debate.deterministic_risk")
_sys.modules[__name__] = _canonical

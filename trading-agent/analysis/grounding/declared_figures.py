"""Shim module: monika.application.analysis.grounding.declared_figures."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.grounding.declared_figures import *

_canonical = _importlib.import_module("monika.application.analysis.grounding.declared_figures")
_sys.modules[__name__] = _canonical

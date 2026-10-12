"""Shim module: monika.application.analysis.debate.bull_analyst."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.debate.bull_analyst import *

_canonical = _importlib.import_module("monika.application.analysis.debate.bull_analyst")
_sys.modules[__name__] = _canonical

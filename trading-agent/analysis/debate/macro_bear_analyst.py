"""Shim module: monika.application.analysis.debate.macro_bear_analyst."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.debate.macro_bear_analyst import *

_canonical = _importlib.import_module("monika.application.analysis.debate.macro_bear_analyst")
_sys.modules[__name__] = _canonical

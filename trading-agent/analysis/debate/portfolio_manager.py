"""Shim module: monika.application.analysis.debate.portfolio_manager."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.debate.portfolio_manager import *

_canonical = _importlib.import_module("monika.application.analysis.debate.portfolio_manager")
_sys.modules[__name__] = _canonical

"""Shim module: monika.application.analysis.debate.investment_judge."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.debate.investment_judge import *

_canonical = _importlib.import_module("monika.application.analysis.debate.investment_judge")
_sys.modules[__name__] = _canonical

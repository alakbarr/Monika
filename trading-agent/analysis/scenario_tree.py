"""Shim module: monika.application.analysis.scenario_tree."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.scenario_tree import *

_canonical = _importlib.import_module("monika.application.analysis.scenario_tree")
_sys.modules[__name__] = _canonical

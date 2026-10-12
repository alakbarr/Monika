"""Shim module: monika.application.analysis.memory.skill_evolution."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.skill_evolution import *

_canonical = _importlib.import_module("monika.application.analysis.memory.skill_evolution")
_sys.modules[__name__] = _canonical

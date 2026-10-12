"""Shim module: monika.application.analysis.memory.skill_curator."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.skill_curator import *

_canonical = _importlib.import_module("monika.application.analysis.memory.skill_curator")
_sys.modules[__name__] = _canonical

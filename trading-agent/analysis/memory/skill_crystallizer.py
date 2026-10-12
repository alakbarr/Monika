"""Shim module: monika.application.analysis.memory.skill_crystallizer."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.skill_crystallizer import *

_canonical = _importlib.import_module("monika.application.analysis.memory.skill_crystallizer")
_sys.modules[__name__] = _canonical

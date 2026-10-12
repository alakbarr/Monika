"""Shim module: monika.application.analysis.memory.negative_constraint_generator."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.negative_constraint_generator import *

_canonical = _importlib.import_module("monika.application.analysis.memory.negative_constraint_generator")
_sys.modules[__name__] = _canonical

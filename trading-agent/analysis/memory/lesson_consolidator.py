"""Shim module: monika.application.analysis.memory.lesson_consolidator."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.lesson_consolidator import *

_canonical = _importlib.import_module("monika.application.analysis.memory.lesson_consolidator")
_sys.modules[__name__] = _canonical

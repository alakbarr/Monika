"""Shim module: monika.application.analysis.memory.trajectory_compressor."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.trajectory_compressor import *

_canonical = _importlib.import_module("monika.application.analysis.memory.trajectory_compressor")
_sys.modules[__name__] = _canonical

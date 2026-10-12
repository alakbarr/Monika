"""Shim module: monika.application.analysis.subagent_spawner."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.subagent_spawner import *

_canonical = _importlib.import_module("monika.application.analysis.subagent_spawner")
_sys.modules[__name__] = _canonical

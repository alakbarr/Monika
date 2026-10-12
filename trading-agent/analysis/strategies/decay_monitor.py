"""Shim module: monika.application.analysis.strategies.decay_monitor."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.strategies.decay_monitor import *

_canonical = _importlib.import_module("monika.application.analysis.strategies.decay_monitor")
_sys.modules[__name__] = _canonical

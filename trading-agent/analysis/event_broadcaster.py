"""Shim module: monika.application.analysis.event_broadcaster."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.event_broadcaster import *

_canonical = _importlib.import_module("monika.application.analysis.event_broadcaster")
_sys.modules[__name__] = _canonical

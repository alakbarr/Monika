"""Shim module: monika.application.analysis.arbitration.signal_arbitrator."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.arbitration.signal_arbitrator import *

_canonical = _importlib.import_module("monika.application.analysis.arbitration.signal_arbitrator")
_sys.modules[__name__] = _canonical

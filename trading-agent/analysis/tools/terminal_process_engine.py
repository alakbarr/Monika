"""Shim module: monika.application.analysis.tools.terminal_process_engine."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.terminal_process_engine import *

_canonical = _importlib.import_module("monika.application.analysis.tools.terminal_process_engine")
_sys.modules[__name__] = _canonical

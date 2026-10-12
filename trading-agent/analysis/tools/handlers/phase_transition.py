"""Shim module: monika.application.analysis.tools.handlers.phase_transition."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.handlers.phase_transition import *

_canonical = _importlib.import_module("monika.application.analysis.tools.handlers.phase_transition")
_sys.modules[__name__] = _canonical

"""Shim module: monika.application.analysis.tools.handlers.analysis_submit."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.handlers.analysis_submit import *

_canonical = _importlib.import_module("monika.application.analysis.tools.handlers.analysis_submit")
_sys.modules[__name__] = _canonical

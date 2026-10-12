"""Shim module: monika.application.analysis.tools.handlers.analytical_query_builder."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.handlers.analytical_query_builder import *

_canonical = _importlib.import_module("monika.application.analysis.tools.handlers.analytical_query_builder")
_sys.modules[__name__] = _canonical

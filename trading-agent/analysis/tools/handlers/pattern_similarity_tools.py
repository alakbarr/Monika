"""Shim module: monika.application.analysis.tools.handlers.pattern_similarity_tools."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.handlers.pattern_similarity_tools import *

_canonical = _importlib.import_module("monika.application.analysis.tools.handlers.pattern_similarity_tools")
_sys.modules[__name__] = _canonical

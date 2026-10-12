"""Shim module: monika.application.analysis.tools.core.coercion."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.core.coercion import *

_canonical = _importlib.import_module("monika.application.analysis.tools.core.coercion")
_sys.modules[__name__] = _canonical

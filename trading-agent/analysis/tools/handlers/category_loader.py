"""Shim module: monika.application.analysis.tools.handlers.category_loader."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.handlers.category_loader import *

_canonical = _importlib.import_module("monika.application.analysis.tools.handlers.category_loader")
_sys.modules[__name__] = _canonical

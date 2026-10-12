"""Shim module: monika.application.analysis.tools.handlers.verified_snapshot."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.handlers.verified_snapshot import *

_canonical = _importlib.import_module("monika.application.analysis.tools.handlers.verified_snapshot")
_sys.modules[__name__] = _canonical

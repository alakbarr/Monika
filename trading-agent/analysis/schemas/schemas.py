"""Shim module: monika.application.analysis.schemas.schemas."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.schemas.schemas import *

_canonical = _importlib.import_module("monika.application.analysis.schemas.schemas")
_sys.modules[__name__] = _canonical

"""Shim module: monika.application.analysis.prompt_sections."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.prompt_sections import *

_canonical = _importlib.import_module("monika.application.analysis.prompt_sections")
_sys.modules[__name__] = _canonical

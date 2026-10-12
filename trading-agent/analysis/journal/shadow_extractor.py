"""Shim module: monika.application.analysis.journal.shadow_extractor."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.journal.shadow_extractor import *

_canonical = _importlib.import_module("monika.application.analysis.journal.shadow_extractor")
_sys.modules[__name__] = _canonical

"""Shim module: monika.application.analysis.memory.sharegpt_exporter."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.sharegpt_exporter import *

_canonical = _importlib.import_module("monika.application.analysis.memory.sharegpt_exporter")
_sys.modules[__name__] = _canonical

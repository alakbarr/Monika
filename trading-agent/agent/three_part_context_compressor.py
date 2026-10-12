"""Shim module: monika.application.agent.three_part_context_compressor."""
import sys as _sys
import importlib as _importlib

from monika.application.agent.three_part_context_compressor import *

_canonical = _importlib.import_module("monika.application.agent.three_part_context_compressor")
_sys.modules[__name__] = _canonical

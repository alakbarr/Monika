"""Shim module: monika.application.analysis.grounding.surgical_redaction."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.grounding.surgical_redaction import *

_canonical = _importlib.import_module("monika.application.analysis.grounding.surgical_redaction")
_sys.modules[__name__] = _canonical

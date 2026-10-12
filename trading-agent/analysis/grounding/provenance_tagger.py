"""Shim module: monika.application.analysis.grounding.provenance_tagger."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.grounding.provenance_tagger import *

_canonical = _importlib.import_module("monika.application.analysis.grounding.provenance_tagger")
_sys.modules[__name__] = _canonical

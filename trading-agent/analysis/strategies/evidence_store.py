"""Shim module: monika.application.analysis.strategies.evidence_store."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.strategies.evidence_store import *

_canonical = _importlib.import_module("monika.application.analysis.strategies.evidence_store")
_sys.modules[__name__] = _canonical

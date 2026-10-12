"""Shim module: monika.application.analysis.stages.per_asset.verifiers."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.stages.per_asset.verifiers import *

_canonical = _importlib.import_module("monika.application.analysis.stages.per_asset.verifiers")
_sys.modules[__name__] = _canonical

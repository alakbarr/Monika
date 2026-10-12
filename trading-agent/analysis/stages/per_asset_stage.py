"""Shim module: monika.application.analysis.stages.per_asset_stage."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.stages.per_asset_stage import *

_canonical = _importlib.import_module("monika.application.analysis.stages.per_asset_stage")
_sys.modules[__name__] = _canonical

"""Shim module: monika.application.analysis.stages.per_asset.specialist_pipeline."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.stages.per_asset.specialist_pipeline import *

_canonical = _importlib.import_module("monika.application.analysis.stages.per_asset.specialist_pipeline")
_sys.modules[__name__] = _canonical

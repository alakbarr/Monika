"""Shim module: monika.application.analysis.stages.per_asset.specialist_council."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.stages.per_asset.specialist_council import *

_canonical = _importlib.import_module("monika.application.analysis.stages.per_asset.specialist_council")
_sys.modules[__name__] = _canonical

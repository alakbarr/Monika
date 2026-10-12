"""Shim module: monika.application.plugins.analysis_pipelines.macro_to_asset.macro_to_asset_pipeline."""

import sys as _sys
import importlib as _importlib

from monika.application.plugins.analysis_pipelines.macro_to_asset.macro_to_asset_pipeline import *

_canonical = _importlib.import_module("monika.application.plugins.analysis_pipelines.macro_to_asset.macro_to_asset_pipeline")
_sys.modules[__name__] = _canonical

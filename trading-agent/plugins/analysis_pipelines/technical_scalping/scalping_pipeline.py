"""Shim module: monika.application.plugins.analysis_pipelines.technical_scalping.scalping_pipeline."""

import sys as _sys
import importlib as _importlib

from monika.application.plugins.analysis_pipelines.technical_scalping.scalping_pipeline import *

_canonical = _importlib.import_module("monika.application.plugins.analysis_pipelines.technical_scalping.scalping_pipeline")
_sys.modules[__name__] = _canonical
